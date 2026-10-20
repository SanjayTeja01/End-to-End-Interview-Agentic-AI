"""Tenant-scoped data access helpers. Use these instead of raw `db.get` for tenant-owned rows."""
from __future__ import annotations

import uuid
from typing import TypeVar

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.core.errors import NotFound

T = TypeVar("T")


def scoped_select(model: type[T], user: CurrentUser) -> Select:
    return select(model).where(model.institute_id == user.institute_id)  # type: ignore[attr-defined]


def get_scoped(db: Session, model: type[T], obj_id: uuid.UUID, user: CurrentUser, *, label: str | None = None) -> T:
    """Fetch a row only if it belongs to the caller's institution. Cross-tenant ids yield 404 (no existence leak)."""
    obj = db.execute(scoped_select(model, user).where(model.id == obj_id)).scalar_one_or_none()  # type: ignore[attr-defined]
    if obj is None:
        raise NotFound(f"{label or model.__name__} not found")
    return obj


def ensure_own_candidate(user: CurrentUser, candidate_id: uuid.UUID) -> None:
    """Students may only touch their own candidate records."""
    if user.is_student and user.id != candidate_id:
        raise NotFound("Not found")
