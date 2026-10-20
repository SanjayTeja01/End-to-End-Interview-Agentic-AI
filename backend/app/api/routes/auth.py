from __future__ import annotations

import re
import secrets

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, require_institution_admin, resolve_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import Conflict, NotFound, Unauthorized
from app.core.logging import log_event
from app.core.security import create_token, hash_password, verify_password
from app.models import CandidateProfile, Institution, User
from app.models.base import utcnow
from app.models.enums import UserRole
from app.schemas.auth import LoginIn, MeOut, RefreshIn, RegisterIn, StaffCreateIn, TokenOut
from app.services.rate_limit import enforce

import logging

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])
REFRESH_COOKIE = "ia_refresh"


def _issue(response: Response, user: User) -> TokenOut:
    s = get_settings()
    access = create_token(user_id=user.id, role=user.role, institute_id=user.institute_id, token_type="access")
    refresh = create_token(user_id=user.id, role=user.role, institute_id=user.institute_id, token_type="refresh")
    response.set_cookie(REFRESH_COOKIE, refresh, httponly=True, secure=s.cookie_secure, samesite="strict",
                        max_age=s.refresh_token_days * 86400, path="/")
    return TokenOut(access_token=access, expires_in=s.access_token_minutes * 60)


def _slug(name: str) -> str:
    return (re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "institution") + "-" + secrets.token_hex(3)


@router.post("/register", response_model=TokenOut, status_code=201)
def register(data: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)) -> TokenOut:
    enforce(f"register:{request.client.host if request.client else 'x'}", 10, 3600, "Too many registrations")
    email = data.email.lower()
    if db.execute(select(User.id).where(User.email == email)).first():
        raise Conflict("An account with this email already exists")
    if data.account_type == "institution":
        inst = Institution(name=data.institution_name.strip(), slug=_slug(data.institution_name),
                           join_code=secrets.token_urlsafe(6).upper()[:8])
        db.add(inst)
        db.flush()
        user = User(institute_id=inst.id, email=email, password_hash=hash_password(data.password),
                    full_name=data.full_name.strip(), role=UserRole.INSTITUTION_ADMIN)
        db.add(user)
    else:
        inst = db.execute(select(Institution).where(Institution.join_code == data.institution_code.strip().upper(),
                                                    Institution.status == "active")).scalar_one_or_none()
        if inst is None:
            raise NotFound("Institution code not recognised")
        user = User(institute_id=inst.id, email=email, password_hash=hash_password(data.password),
                    full_name=data.full_name.strip(), role=UserRole.STUDENT)
        db.add(user)
        db.flush()
        db.add(CandidateProfile(user_id=user.id, institute_id=inst.id))
    db.commit()
    log_event(log, "user_registered", user_id=str(user.id), role=user.role, institute_id=str(user.institute_id))
    return _issue(response, user)


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> TokenOut:
    email = data.email.lower()
    enforce(f"login:{email}", 10, 300, "Too many login attempts, try again later")
    enforce(f"login-ip:{request.client.host if request.client else 'x'}", 50, 300, "Too many login attempts")
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None or not verify_password(data.password, user.password_hash) or user.status != "active":
        log_event(log, "login_failed", email_domain=email.split("@")[-1])
        raise Unauthorized("Invalid email or password")
    user.last_login_at = utcnow()
    db.commit()
    log_event(log, "login", user_id=str(user.id), role=user.role)
    return _issue(response, user)


@router.post("/refresh", response_model=TokenOut)
def refresh(request: Request, response: Response, body: RefreshIn | None = None, db: Session = Depends(get_db)) -> TokenOut:
    token = request.cookies.get(REFRESH_COOKIE) or (body.refresh_token if body else None)
    if not token:
        raise Unauthorized("No refresh token")
    cu = resolve_user(db, token, expected_type="refresh")
    return _issue(response, db.get(User, cu.id))


@router.post("/logout", status_code=204)
def logout(response: Response) -> Response:
    response.delete_cookie(REFRESH_COOKIE, path="/")
    response.status_code = 204
    return response


@router.get("/me", response_model=MeOut)
def me(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> MeOut:
    inst = db.get(Institution, user.institute_id)
    return MeOut(id=user.id, email=user.email, full_name=user.full_name, role=user.role, institute_id=user.institute_id,
                 institution_name=inst.name, institution_join_code=inst.join_code if user.is_institution else None)


@router.post("/staff", status_code=201)
def create_staff(data: StaffCreateIn, user: CurrentUser = Depends(require_institution_admin),
                 db: Session = Depends(get_db)) -> dict:
    email = data.email.lower()
    if db.execute(select(User.id).where(User.email == email)).first():
        raise Conflict("An account with this email already exists")
    staff = User(institute_id=user.institute_id, email=email, password_hash=hash_password(data.password),
                 full_name=data.full_name, role=UserRole.INSTITUTION_STAFF)
    db.add(staff)
    db.commit()
    return {"id": str(staff.id), "email": staff.email, "role": staff.role}
