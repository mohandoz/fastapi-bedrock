"""Authentication business logic: registration, login, token rotation and account lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal
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
from {{ cookiecutter.package_name }}.core.exceptions import (
    ConflictError,
    ForbiddenError,
    UnauthorizedError,
)
from {{ cookiecutter.package_name }}.core.security import (
    create_access_token,
    create_email_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_and_update_password,
    verify_password,
    verify_password_dummy,
)
from {{ cookiecutter.package_name }}.domains.auth.models import User
from {{ cookiecutter.package_name }}.domains.auth.repository import UserRepository
from {{ cookiecutter.package_name }}.domains.auth.schemas import Token, UserCreate
from {{ cookiecutter.package_name }}.domains.auth.token_store import RefreshTokenStore

logger = structlog.get_logger(__name__)

# Single-purpose token types for links embedded in emails. They share the JWT
# machinery in core/security.py, so an email token can never pass an access- or
# refresh-token type check (and vice versa).
EmailTokenType = Literal["password_reset", "email_verification"]


class AuthService:
    def __init__(
        self,
        repository: UserRepository,
        token_store: RefreshTokenStore,
        email_backend: EmailBackend | None = None,
    ) -> None:
        self.repository = repository
        self.token_store = token_store
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
        return user

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.repository.get_by_email(email.lower())
        if user is None:
            # Burn an Argon2 verification so unknown and known emails cost the
            # same time, closing a user-enumeration timing oracle.
            await run_in_threadpool(verify_password_dummy, password)
            raise UnauthorizedError("Incorrect email or password")
        valid, updated_hash = await run_in_threadpool(
            verify_and_update_password, password, user.hashed_password
        )
        if not valid:
            raise UnauthorizedError("Incorrect email or password")
        if not user.is_active:
            raise UnauthorizedError("Inactive user")
        if settings.require_email_verification and not user.is_verified:
            raise UnauthorizedError("Email address not verified")
        if updated_hash is not None:
            # Argon2 parameters strengthened since this hash was minted;
            # transparently rehash while we hold the plaintext.
            user = await self.repository.update(user, {"hashed_password": updated_hash})
            logger.info("auth.password_rehashed", user_id=str(user.id))
        return user

    async def issue_tokens(self, user: User, *, family: str | None = None) -> Token:
        """Mint an access/refresh pair, registering the refresh jti with the store.

        Passing ``family`` continues an existing rotation chain (refresh);
        omitting it starts a new one (login).
        """
        jti = uuid4().hex
        family = family if family is not None else uuid4().hex
        expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
        await self.token_store.store(jti=jti, family=family, user_id=user.id, expires_at=expires_at)
        return Token(
            access_token=create_access_token(user.id, version=user.auth_version),
            refresh_token=create_refresh_token(
                user.id,
                jti=jti,
                family=family,
                version=user.auth_version,
            ),
        )

    async def refresh_tokens(self, refresh_token: str) -> Token:
        """Rotate a refresh token: the presented jti is invalidated on success."""
        user_id, jti, family, version = self._refresh_claims(refresh_token)
        user = await self.repository.get(user_id)
        if user is None or not user.is_active or user.auth_version != version:
            await self.token_store.revoke_family(family)
            raise UnauthorizedError("User or credentials are no longer valid")
        new_jti = uuid4().hex
        expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
        state = await self.token_store.rotate(
            jti=jti,
            new_jti=new_jti,
            family=family,
            user_id=user.id,
            expires_at=expires_at,
        )
        if state == "reused":
            # Replay of an already-rotated token — assume theft and log out
            # every token descended from this login.
            await self.token_store.revoke_family(family)
            logger.warning("auth.refresh_reuse_detected", user_id=str(user_id), family=family)
            raise UnauthorizedError("Invalid refresh token")
        if state != "ok":
            raise UnauthorizedError("Invalid refresh token")
        return Token(
            access_token=create_access_token(user.id, version=user.auth_version),
            refresh_token=create_refresh_token(
                user.id,
                jti=new_jti,
                family=family,
                version=user.auth_version,
            ),
        )

    async def logout(self, refresh_token: str) -> None:
        """Revoke the token's whole family. Access tokens ride out their short expiry."""
        user_id, _jti, family, _version = self._refresh_claims(refresh_token)
        await self.token_store.revoke_family(family)
        logger.info("auth.logout", user_id=str(user_id))

    async def change_password(self, user: User, current_password: str, new_password: str) -> None:
        valid = await run_in_threadpool(verify_password, current_password, user.hashed_password)
        if not valid:
            raise ForbiddenError("Current password is incorrect")
        hashed = await run_in_threadpool(hash_password, new_password)
        changed = await self.repository.update_password_if_version(
            user,
            expected_version=user.auth_version,
            hashed_password=hashed,
        )
        if not changed:
            raise UnauthorizedError("Credentials changed concurrently; authenticate again")
        logger.info("auth.password_changed", user_id=str(user.id))

    async def delete_account(self, user: User) -> None:
{%- if cookiecutter.use_redis == "yes" %}
        """GDPR erasure: hard-delete the user row.

        Refresh-token families in Redis are not enumerable per user; any
        survivors die at the user lookup on their next refresh. Future
        user-owned tables must declare ``ON DELETE CASCADE`` foreign keys (or
        be anonymized here) to keep erasure complete.
        """
{%- else %}
        """GDPR erasure: hard-delete the user row.

        The user's ``refresh_tokens`` rows are deleted with it via ON DELETE
        CASCADE. Future user-owned tables must declare ``ON DELETE CASCADE``
        foreign keys (or be anonymized here) to keep erasure complete.
        """
{%- endif %}
        user_id = user.id
        await self.repository.delete(user)
        logger.info("auth.account_deleted", user_id=str(user_id))

    def _refresh_claims(self, refresh_token: str) -> tuple[UUID, str, str, int]:
        """Validate a refresh JWT and return its identity and rotation claims."""
        try:
            payload = decode_token(refresh_token)
        except jwt.PyJWTError as exc:
            raise UnauthorizedError("Invalid refresh token") from exc
        if payload.get("type") != "refresh":
            raise UnauthorizedError("Invalid token type")
        subject = payload.get("sub")
        jti = payload.get("jti")
        family = payload.get("family")
        version = payload.get("ver")
        if (
            not isinstance(subject, str)
            or not isinstance(jti, str)
            or not isinstance(family, str)
            or not isinstance(version, int)
        ):
            raise UnauthorizedError("Invalid refresh token")
        try:
            user_id = UUID(subject)
        except ValueError as exc:
            raise UnauthorizedError("Invalid refresh token") from exc
        return user_id, jti, family, version

    async def prepare_password_reset(self, email: str) -> EmailMessage | None:
        """Build a reset email without exposing account existence through work cost.

        Delivery is scheduled after the HTTP response starts. Unknown accounts
        still perform token creation and rendering, keeping the synchronous path
        materially equivalent without sending mail to an attacker-controlled
        address.
        """
        user = await self.repository.get_by_email(email.lower())
        active = user is not None and user.is_active
        token = create_email_token(
            user.id if active and user is not None else UUID(int=0),
            "password_reset",
            version=user.auth_version if active and user is not None else 0,
        )
        html, text = render_email(
            "password_reset",
            project_name=settings.project_name,
            link=f"{settings.frontend_url}/reset-password?token={token}",
            expire_minutes=settings.email_token_expire_minutes,
        )
        if not active or user is None:
            logger.info("auth.password_reset_skipped", reason="unknown_or_inactive_email")
            return None
        return EmailMessage(
            to=user.email,
            subject=f"{settings.project_name} — password recovery",
            html=html,
            text=text,
        )

    async def deliver_password_reset(self, message: EmailMessage) -> None:
        """Deliver a prepared reset email after the HTTP response has started."""
        try:
            await self.email_backend.send(message)
        except Exception:
            # The client already received the non-enumerating 202. Record only
            # metadata; the body contains a live token and must never be logged.
            logger.exception("auth.password_reset_delivery_failed", to=message.to)
            return
        logger.info("auth.password_reset_delivered", to=message.to)

    async def reset_password(self, token: str, new_password: str) -> None:
        user = await self._user_from_email_token(token, "password_reset")
        hashed = await run_in_threadpool(hash_password, new_password)
        changed = await self.repository.update_password_if_version(
            user,
            expected_version=user.auth_version,
            hashed_password=hashed,
        )
        if not changed:
            raise UnauthorizedError("Invalid or already-used token")
        logger.info("auth.password_reset", user_id=str(user.id))

    async def verify_email(self, token: str) -> User:
        user = await self._user_from_email_token(token, "email_verification")
        if not user.is_verified:
            user = await self.repository.update(user, {"is_verified": True})
            logger.info("auth.email_verified", user_id=str(user.id))
        return user

    def prepare_verification_email(self, user: User) -> EmailMessage:
        """Build the registration email; the route delivers it after DB commit."""
        return self._build_verification_email(
            user_id=user.id,
            version=user.auth_version,
            to=user.email,
        )

    async def prepare_verification_resend(self, email: str) -> EmailMessage | None:
        """Build a replacement verification email without enumerating accounts."""
        user = await self.repository.get_by_email(email.lower())
        eligible = (
            settings.require_email_verification
            and user is not None
            and user.is_active
            and not user.is_verified
        )
        message = self._build_verification_email(
            user_id=user.id if eligible and user is not None else UUID(int=0),
            version=user.auth_version if eligible and user is not None else 0,
            to=user.email if eligible and user is not None else "discarded@example.invalid",
        )
        if not eligible:
            logger.info("auth.verification_resend_skipped", reason="ineligible_email")
            return None
        return message

    def _build_verification_email(self, *, user_id: UUID, version: int, to: str) -> EmailMessage:
        token = create_email_token(
            user_id,
            "email_verification",
            version=version,
        )
        html, text = render_email(
            "verify_email",
            project_name=settings.project_name,
            link=f"{settings.frontend_url}/verify-email?token={token}",
            expire_minutes=settings.email_token_expire_minutes,
        )
        return EmailMessage(
            to=to,
            subject=f"{settings.project_name} — verify your email",
            html=html,
            text=text,
        )

    async def deliver_verification_email(self, message: EmailMessage) -> None:
        """Deliver verification mail after the response/transaction completes."""
        try:
            await self.email_backend.send(message)
        except Exception:
            logger.exception("auth.verification_delivery_failed", to=message.to)
            return
        logger.info("auth.verification_email_sent", to=message.to)

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
        if payload.get("ver") != user.auth_version:
            raise UnauthorizedError("Invalid or already-used token")
        return user
