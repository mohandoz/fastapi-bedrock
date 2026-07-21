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


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return _password_hash.verify(password, hashed)


def _create_token(subject: str, expires_delta: timedelta, token_type: TokenType) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + expires_delta,
        "jti": uuid.uuid4().hex,
        "type": token_type,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_access_token(subject: str | uuid.UUID) -> str:
    delta = timedelta(minutes=settings.access_token_expire_minutes)
    return _create_token(str(subject), delta, "access")


def create_refresh_token(subject: str | uuid.UUID) -> str:
    delta = timedelta(days=settings.refresh_token_expire_days)
    return _create_token(str(subject), delta, "refresh")


def decode_token(token: str) -> dict[str, Any]:
    """Decode and verify a JWT. Raises ``jwt.PyJWTError`` on failure."""
    return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
