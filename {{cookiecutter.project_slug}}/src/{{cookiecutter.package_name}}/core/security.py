"""Password hashing (Argon2) and JSON Web Token helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from pwdlib import PasswordHash

from {{ cookiecutter.package_name }}.core.config import settings

_password_hash = PasswordHash.recommended()

TokenType = Literal["access", "refresh"]

# Tolerated clock skew (seconds) between the replica that minted a token and
# the replica verifying it.
JWT_LEEWAY = 10


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return _password_hash.verify(password, hashed)


def verify_and_update_password(password: str, hashed: str) -> tuple[bool, str | None]:
    """Verify a password and report whether its hash needs re-hashing.

    The second element is a replacement hash minted with the currently
    recommended Argon2 parameters, or ``None`` when the stored hash is already
    up to date. Persisting it on successful login keeps old hashes from
    surviving parameter upgrades forever.
    """
    return _password_hash.verify_and_update(password, hashed)


# Computed once at import so a login attempt for an unknown email can burn a
# real Argon2 verification, keeping its timing identical to the known-email path.
_dummy_hash = _password_hash.hash("dummy-password")


def verify_password_dummy(password: str) -> None:
    """Verify ``password`` against a throwaway hash and discard the result."""
    _password_hash.verify(password, _dummy_hash)


def _create_token(
    subject: str,
    expires_delta: timedelta,
    token_type: str,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        # aud/iss bind the token to this service: another service generated
        # from this template that shares (or defaults) SECRET_KEY still
        # rejects it.
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + expires_delta,
        "jti": uuid.uuid4().hex,
        "type": token_type,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_access_token(subject: str | uuid.UUID, *, version: int = 0) -> str:
    delta = timedelta(minutes=settings.access_token_expire_minutes)
    return _create_token(str(subject), delta, "access", {"ver": version})


def create_refresh_token(
    subject: str | uuid.UUID, *, jti: str, family: str, version: int = 0
) -> str:
    """Mint a refresh token whose ``jti``/``family`` are tracked by the token store."""
    delta = timedelta(days=settings.refresh_token_expire_days)
    return _create_token(
        str(subject),
        delta,
        "refresh",
        {"jti": jti, "family": family, "ver": version},
    )


def create_email_token(subject: str | uuid.UUID, token_type: str, *, version: int = 0) -> str:
    """Mint a short-lived, single-purpose signed token for an email link."""
    delta = timedelta(minutes=settings.email_token_expire_minutes)
    return _create_token(str(subject), delta, token_type, {"ver": version})


# Every claim _create_token mints is mandatory on the way back in: a token
# missing any of them (hand-rolled, minted by other software sharing the
# secret, or pre-hardening) must not verify. `require` checks presence only —
# exp/iat/aud/iss values are verified by the dedicated options below, and the
# `type` value is asserted at each call site.
_REQUIRED_CLAIMS = ["exp", "iat", "sub", "jti", "type", "iss", "aud", "ver"]


def decode_token(token: str) -> dict[str, Any]:
    """Decode and verify a JWT (signature, expiry, audience, issuer, claims).

    The algorithm list is pinned to the single configured algorithm — never
    derived from the token header. Raises ``jwt.PyJWTError`` on failure.
    """
    return jwt.decode(
        token,
        settings.secret_key,
        algorithms=[settings.algorithm],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
        leeway=JWT_LEEWAY,
        options={"require": _REQUIRED_CLAIMS},
    )
