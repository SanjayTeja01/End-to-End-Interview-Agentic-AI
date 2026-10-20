from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)
    account_type: Literal["student", "institution"]
    # students: code issued by their institution; institutions: new institution name
    institution_code: str | None = Field(default=None, max_length=32)
    institution_name: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _check(self):  # noqa: ANN202
        if self.account_type == "student" and not self.institution_code:
            raise ValueError("institution_code is required for student registration")
        if self.account_type == "institution" and not self.institution_name:
            raise ValueError("institution_name is required for institution registration")
        return self


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class MeOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    institute_id: uuid.UUID
    institution_name: str
    institution_join_code: str | None = None  # only for institution users


class RefreshIn(BaseModel):
    refresh_token: str | None = None  # optional — cookie is preferred


class StaffCreateIn(BaseModel):
    email: EmailStr
    full_name: str
    password: str = Field(min_length=10, max_length=128)
