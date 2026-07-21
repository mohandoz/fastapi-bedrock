"""Liveness and readiness probes for orchestrators and load balancers."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from {{ cookiecutter.package_name }}.core.database import get_session

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness probe")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe (verifies the database)")
async def ready(session: Annotated[AsyncSession, Depends(get_session)]) -> dict[str, str]:
    await session.execute(text("SELECT 1"))
    return {"status": "ready"}
