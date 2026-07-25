"""Startup bootstrap: ensure the configured FIRST_SUPERUSER account exists."""

from __future__ import annotations

import structlog
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import IntegrityError

from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.core.database import async_session_factory
from {{ cookiecutter.package_name }}.core.security import hash_password
from {{ cookiecutter.package_name }}.domains.auth.models import User
from {{ cookiecutter.package_name }}.domains.auth.repository import UserRepository

logger = structlog.get_logger(__name__)


async def ensure_first_superuser() -> None:
    """Create or promote the FIRST_SUPERUSER account. No-op unless configured.

    Called from the lifespan on every startup; idempotent, and safe to run
    from multiple replicas (the unique email constraint settles the race).
    The account is created verified so login works with email verification on.
    """
    if not settings.first_superuser_email or not settings.first_superuser_password:
        return
    email = settings.first_superuser_email.lower()
    async with async_session_factory() as session:
        repository = UserRepository(session)
        user = await repository.get_by_email(email)
        if user is None:
            hashed = await run_in_threadpool(hash_password, settings.first_superuser_password)
            try:
                await repository.add(
                    User(email=email, hashed_password=hashed, is_superuser=True, is_verified=True)
                )
                await session.commit()
            except IntegrityError:  # another replica created it first
                await session.rollback()
                return
            logger.info("auth.first_superuser_created", email=email)
        elif not user.is_superuser:
            await repository.update(user, {"is_superuser": True})
            await session.commit()
            logger.info("auth.first_superuser_promoted", email=email)
