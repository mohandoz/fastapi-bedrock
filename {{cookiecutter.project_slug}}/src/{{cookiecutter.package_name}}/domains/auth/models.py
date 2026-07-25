"""User model for authentication."""

from __future__ import annotations

from pydantic import EmailStr
from sqlmodel import Field, SQLModel

from {{ cookiecutter.package_name }}.core.models import TimestampMixin, UUIDMixin


class UserBase(SQLModel):
    email: EmailStr = Field(index=True, unique=True)
    full_name: str | None = Field(default=None, max_length=255)
    is_active: bool = Field(default=True)
    # Only enforced at login when REQUIRE_EMAIL_VERIFICATION is enabled.
    is_verified: bool = Field(default=False)
    is_superuser: bool = Field(default=False)


class User(UserBase, UUIDMixin, TimestampMixin, table=True):
    __tablename__ = "users"

    hashed_password: str
