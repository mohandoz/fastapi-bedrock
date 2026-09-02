"""User{% if cookiecutter.use_redis == "no" %} and refresh-token models{% else %} model{% endif %} for authentication."""

from __future__ import annotations

{% if cookiecutter.use_redis == "no" -%}
import uuid
from datetime import datetime

from pydantic import EmailStr
from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel
{%- else -%}
from pydantic import EmailStr
from sqlmodel import Field, SQLModel
{%- endif %}

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
    # Incremented on every password change/reset. Tokens carry the version they
    # were issued under, so changing credentials invalidates every old session
    # and makes password-reset links single-use without a separate token table.
    auth_version: int = Field(default=0, nullable=False)
{%- if cookiecutter.use_redis == "no" %}


class RefreshToken(SQLModel, table=True):
    """One row per issued refresh token (see ``domains/auth/token_store.py``).

    ``ON DELETE CASCADE`` ties rows to their user, so GDPR account erasure
    removes them in the same statement.
    """

    __tablename__ = "refresh_tokens"

    jti: str = Field(primary_key=True, max_length=32)
    family: str = Field(index=True, max_length=32)
    user_id: uuid.UUID = Field(foreign_key="users.id", ondelete="CASCADE", index=True)
    # sa_type accepts a type instance at runtime; the SQLModel stub types it as a class.
    expires_at: datetime = Field(sa_type=DateTime(timezone=True))  # type: ignore[call-overload]
    revoked_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
    )
{%- endif %}
