"""Password hashing (Argon2id) and JWT issuing/validation."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import get_settings
from app.core.errors import Unauthorized

_hasher = PasswordHasher()

TokenType = Literal["access", "refresh", "ws"]


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def _secret() -> str:
    secret = get_settings().jwt_secret.get_secret_value()
    if not secret:
        raise RuntimeError("JWT_SECRET is not configured")
    return secret


def create_token(*, user_id: uuid.UUID, role: str, institute_id: uuid.UUID | None, token_type: TokenType,
                 expires: timedelta | None = None, extra: dict[str, Any] | None = None) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    if expires is None:
        expires = timedelta(minutes=s.access_token_minutes) if token_type == "access" else timedelta(days=s.refresh_token_days)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "inst": str(institute_id) if institute_id else None,
        "typ": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, _secret(), algorithm=s.jwt_algorithm)


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any]:
    s = get_settings()
    try:
        payload = jwt.decode(token, _secret(), algorithms=[s.jwt_algorithm], options={"require": ["exp", "sub", "typ"]})
    except jwt.ExpiredSignatureError as exc:
        raise Unauthorized("Token expired", code="token_expired") from exc
    except jwt.PyJWTError as exc:
        raise Unauthorized("Invalid token", code="token_invalid") from exc
    if payload.get("typ") != expected_type:
        raise Unauthorized("Wrong token type", code="token_invalid")
    return payload
