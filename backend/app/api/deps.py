"""Authentication & authorization dependencies. Every request is resolved to a user AND an institute_id
taken from the database — never from client-supplied parameters."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import Forbidden, Unauthorized
from app.core.security import decode_token
from app.models import User
from app.models.enums import INSTITUTION_ROLES, UserRole


@dataclass(frozen=True)
class CurrentUser:
    id: uuid.UUID
    institute_id: uuid.UUID
    role: str
    email: str
    full_name: str

    @property
    def is_institution(self) -> bool:
        return self.role in INSTITUTION_ROLES

    @property
    def is_student(self) -> bool:
        return self.role == UserRole.STUDENT


def _bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise Unauthorized("Missing bearer token")
    return token


def resolve_user(db: Session, token: str, expected_type: str = "access") -> CurrentUser:
    payload = decode_token(token, expected_type)  # type: ignore[arg-type]
    try:
        uid = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise Unauthorized("Invalid token subject") from exc
    user = db.get(User, uid)
    if user is None or user.status != "active" or user.institute_id is None:
        raise Unauthorized("User not found or inactive")
    # Role/tenant come from the DB row, so a stale or tampered claim cannot widen access.
    if payload.get("inst") != str(user.institute_id) or payload.get("role") != user.role:
        raise Unauthorized("Token no longer matches account")
    return CurrentUser(id=user.id, institute_id=user.institute_id, role=user.role, email=user.email, full_name=user.full_name)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> CurrentUser:
    return resolve_user(db, _bearer(request))


def require_institution(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not user.is_institution:
        raise Forbidden("Institution access required")
    return user


def require_institution_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role != UserRole.INSTITUTION_ADMIN:
        raise Forbidden("Institution administrator access required")
    return user


def require_student(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not user.is_student:
        raise Forbidden("Student access required")
    return user
