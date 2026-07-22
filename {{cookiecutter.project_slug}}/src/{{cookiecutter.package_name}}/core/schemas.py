"""Reusable, domain-agnostic API schemas."""

from __future__ import annotations

from pydantic import BaseModel


class Page[ItemT](BaseModel):
    """A paginated list response usable by any domain."""

    items: list[ItemT]
    total: int
    offset: int
    limit: int
