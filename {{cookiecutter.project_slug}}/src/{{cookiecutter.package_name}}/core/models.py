"""Reusable SQLModel mixins for primary keys and timestamps."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, func
from sqlmodel import Field, SQLModel

# Deterministic constraint/index names so Alembic migrations can drop or alter
# them later (see https://alembic.sqlalchemy.org/en/latest/naming.html).
# Every model module imports this one, so the convention is set before any
# table registers on the metadata.
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
SQLModel.metadata.naming_convention = NAMING_CONVENTION


def _utcnow() -> datetime:
    return datetime.now(UTC)


class UUIDMixin(SQLModel):
    """Adds a UUID primary key."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)


class TimestampMixin(SQLModel):
    """Adds database-managed ``created_at`` / ``updated_at`` columns."""

    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now(), "nullable": False},
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={
            "server_default": func.now(),
            "onupdate": func.now(),
            "nullable": False,
        },
    )
