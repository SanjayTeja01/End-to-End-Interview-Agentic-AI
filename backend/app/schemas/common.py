from __future__ import annotations

import uuid
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int


class JobOut(ORM):
    id: uuid.UUID
    job_type: str
    status: str
    entity_type: str | None
    entity_id: uuid.UUID | None
    error: str | None
    result: dict
    created_at: datetime
    updated_at: datetime


class Message(BaseModel):
    message: str
