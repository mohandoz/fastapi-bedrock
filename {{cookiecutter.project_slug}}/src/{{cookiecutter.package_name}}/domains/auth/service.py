"""Authentication business logic: registration, login, token refresh and email flows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid4

import jwt
import structlog
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import IntegrityError

from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.core.email import (
    EmailBackend,
    EmailMessage,
    get_email_backend,
    render_email,
)
from {{ cookiecutter.package_name }}.core.exceptions import ConflictError, UnauthorizedError
from {{ cookiecutter.package_name }}.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
    verify_password_dummy,
)
from {{ cookiecutter.package_name }}.domains.auth.models import User
from {{ cookiecutter.package_name }}.domains.auth.repository import UserRepository
from {{ cookiecutter.package_name }}.domains.auth.schemas import Token, UserCreate

logger = structlog.get_logger(__name__)

# Single-purpose token types for links embedded in emails. They share the JWT
# machinery in core/security.py, so an email token can never pass an access- or
# refresh-token type check (and vice versa).
EmailTokenType = Literal["password_reset", "email_verification"]


def create_email_token(subject: str | UUID, token_type: EmailTokenType) -> str:
    """Mint a short-lived, single-purpose signed token for an email link."""
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": now,
        "exp": now + timedelta(minutes=settings.email_token_expire_minutes),
        "jti": uuid4().hex,
        "type": token_type,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


class AuthService:
    def __init__(
        self, repository: UserRepository, email_backend: EmailBackend | None = None
    ) -> None:
        self.repository = repository
        self.email_backend = email_backend if email_backend is not None else get_email_backend()

    async def register(self, data: UserCreate) -> User:
        # Emails are stored and matched lowercase (EmailStr only lowercases the domain).
        email = data.email.lower()
        if await self.repository.get_by_email(email) is not None:
            raise ConflictError("A user with this email already exists")
        # Argon2 hashing is deliberately CPU-bound; keep it off the event loop.
        hashed = await run_in_threadpool(hash_password, data.password)
        user = User(email=email, full_name=data.full_name, hashed_password=hashed)
        try:
            user = await self.repository.add(user)
        except IntegrityError as exc:  # lost a concurrent-registration race
            raise ConflictError("A user with this email already exists") from exc
        if settings.require_email_verification:
            await self._send_verification_email(user)
        return user

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.repository.get_by_email(email.lower())
        if user is None:
            # Burn an Argon2 verification so unknown and known emails cost the
            # same time, closing a user-enumeration timing oracle.
            await run_in_threadpool(verify_password_dummy, password)
            raise UnauthorizedError("Incorrect email or password")
        valid = await run_in_threadpool(verify_password, password, user.hashed_password)
        if not valid:
            raise UnauthorizedError("Incorrect email or password")
        if not user.is_active:
            raise UnauthorizedError("Inactive user")
        if settings.require_email_verification and not user.is_verified:
            raise UnauthorizedError("Email address not verified")
        return user

    def issue_tokens(self, user: User) -> Token:
        return Token(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
        )

    async def refresh_tokens(self, refresh_token: str) -> Token:
        try:
            payload = decode_token(refresh_token)
        except jwt.PyJWTError as exc:
            raise UnauthorizedError("Invalid refresh token") from exc
        if payload.get("type") != "refresh":
            raise UnauthorizedError("Invalid token type")
        subject = payload.get("sub")
        if subject is None:
            raise UnauthorizedError("Invalid refresh token")
        try:
            user_id = UUID(subject)
        except ValueError as exc:
            raise UnauthorizedError("Invalid refresh token") from exc
        user = await self.repository.get(user_id)
        if user is None or not user.is_active:
            raise UnauthorizedError("User is no longer valid")
        return self.issue_tokens(user)

    async def request_password_reset(self, email: str) -> None:
        """Email a password-reset link. No-ops for unknown or inactive accounts.

        The caller must return the same response either way, so this endpoint
        cannot be used to probe which emails have accounts.
        """
        user = await self.repository.get_by_email(email.lower())
        if user is None or not user.is_active:
            logger.info("auth.password_reset_skipped", reason="unknown_or_inactive_email")
            return
        token = create_email_token(user.id, "password_reset")
        html, text = render_email(
            "password_reset",
            project_name=settings.project_name,
            link=f"{settings.frontend_url}/reset-password?token={token}",
            expire_minutes=settings.email_token_expire_minutes,
        )
        await self.email_backend.send(
            EmailMessage(
                to=user.email,
                subject=f"{settings.project_name} — password recovery",
                html=html,
                text=text,
            )
        )
        logger.info("auth.password_reset_requested", user_id=str(user.id))

    async def reset_password(self, token: str, new_password: str) -> None:
        user = await self._user_from_email_token(token, "password_reset")
        hashed = await run_in_threadpool(hash_password, new_password)
        await self.repository.update(user, {"hashed_password": hashed})
        logger.info("auth.password_reset", user_id=str(user.id))

    async def verify_email(self, token: str) -> User:
        user = await self._user_from_email_token(token, "email_verification")
        if not user.is_verified:
            user = await self.repository.update(user, {"is_verified": True})
            logger.info("auth.email_verified", user_id=str(user.id))
        return user

    async def _send_verification_email(self, user: User) -> None:
        token = create_email_token(user.id, "email_verification")
        html, text = render_email(
            "verify_email",
            project_name=settings.project_name,
            link=f"{settings.frontend_url}/verify-email?token={token}",
            expire_minutes=settings.email_token_expire_minutes,
        )
        await self.email_backend.send(
            EmailMessage(
                to=user.email,
                subject=f"{settings.project_name} — verify your email",
                html=html,
                text=text,
            )
        )
        logger.info("auth.verification_email_sent", user_id=str(user.id))

    async def _user_from_email_token(self, token: str, expected_type: EmailTokenType) -> User:
        try:
            payload = decode_token(token)
        except jwt.PyJWTError as exc:
            raise UnauthorizedError("Invalid or expired token") from exc
        if payload.get("type") != expected_type:
            raise UnauthorizedError("Invalid token type")
        subject = payload.get("sub")
        if subject is None:
            raise UnauthorizedError("Invalid token")
        try:
            user_id = UUID(subject)
        except ValueError as exc:
            raise UnauthorizedError("Invalid token") from exc
        user = await self.repository.get(user_id)
        if user is None or not user.is_active:
            raise UnauthorizedError("User is no longer valid")
        return user
