"""Reusable SQLModel mixins for primary keys and timestamps."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, func
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class UUIDMixin(SQLModel):
    """Adds a UUID primary key."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)


class TimestampMixin(SQLModel):
    """Adds database-managed ``created_at`` / ``updated_at`` columns."""

    # sa_type accepts a type instance at runtime; the SQLModel stub types it as a class.
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        sa_column_kwargs={"server_default": func.now(), "nullable": False},
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        sa_column_kwargs={
            "server_default": func.now(),
            "onupdate": func.now(),
            "nullable": False,
        },
    )
