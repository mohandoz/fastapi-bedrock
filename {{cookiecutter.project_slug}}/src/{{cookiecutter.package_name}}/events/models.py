"""Transactional outbox table.

Events are written here in the SAME database transaction as the domain change,
then a relay forwards them to the stream — removing the dual-write race between
committing to the DB and publishing to the broker.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from {{ cookiecutter.package_name }}.core.models import TimestampMixin, UUIDMixin


class OutboxEvent(UUIDMixin, TimestampMixin, table=True):
    __tablename__ = "outbox_events"

    event_type: str = Field(index=True, max_length=255)
    payload: dict[str, Any] = Field(sa_type=JSONB)
    published_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"nullable": True, "index": True},
    )
