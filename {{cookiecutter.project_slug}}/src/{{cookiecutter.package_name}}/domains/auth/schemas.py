"""Authentication request and response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import EmailStr
from sqlmodel import Field, SQLModel

from {{ cookiecutter.package_name }}.domains.auth.models import UserBase


class UserCreate(SQLModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


class UserRead(UserBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class Token(SQLModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105


class RefreshRequest(SQLModel):
    refresh_token: str


class Message(SQLModel):
    detail: str


class PasswordResetRequest(SQLModel):
    email: EmailStr


class PasswordResetConfirm(SQLModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class PasswordChange(SQLModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class EmailVerificationRequest(SQLModel):
    token: str


class EmailVerificationResendRequest(SQLModel):
    email: EmailStr


class UserExport(SQLModel):
    """Everything the service stores about an account (GDPR data portability)."""

    user: UserRead
    exported_at: datetime
