"""Tests for the authentication endpoints, token lifecycle and email flows."""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import Mock

import jwt
import pytest
from httpx import AsyncClient
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from {{ cookiecutter.package_name }}.core import email as email_module
from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.core.email import ConsoleEmailBackend, EmailMessage
from {{ cookiecutter.package_name }}.core.exceptions import ForbiddenError
from {{ cookiecutter.package_name }}.core.security import create_email_token, decode_token
from {{ cookiecutter.package_name }}.domains.auth import bootstrap
from {{ cookiecutter.package_name }}.domains.auth import service as auth_service
from {{ cookiecutter.package_name }}.domains.auth.dependencies import get_current_superuser
from {{ cookiecutter.package_name }}.domains.auth.models import User

API = settings.api_v1_prefix


class CapturingEmailBackend:
    """Collects rendered emails instead of delivering them."""

    def __init__(self) -> None:
        self.messages: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        self.messages.append(message)


class FailingEmailBackend:
    async def send(self, message: EmailMessage) -> None:
        raise OSError("SMTP unavailable")


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> CapturingEmailBackend:
    """Capture outbound email for the duration of a test."""
    backend = CapturingEmailBackend()
    monkeypatch.setattr(auth_service, "get_email_backend", lambda: backend)
    return backend


def _token_from(message: EmailMessage) -> str:
    match = re.search(r"token=([A-Za-z0-9_\-.]+)", message.text)
    assert match is not None, "email does not contain a token link"
    return match.group(1)


async def test_console_email_redacts_token_body_outside_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger = Mock()
    monkeypatch.setattr(email_module, "logger", logger)
    monkeypatch.setattr(settings, "environment", "production")
    await ConsoleEmailBackend().send(
        EmailMessage(
            to="user@example.com",
            subject="Password reset",
            text="https://example.com/reset?token=live-secret",
            html="<a>live-secret</a>",
        )
    )
    logger.warning.assert_called_once()
    assert "body" not in logger.warning.call_args.kwargs


async def _register_and_login(client: AsyncClient, email: str, secret: str) -> dict[str, str]:
    await client.post(f"{API}/auth/register", json={"email": email, "password": secret})
    response = await client.post(f"{API}/auth/login", data={"username": email, "password": secret})
    return response.json()


def _make_token(token_type: str, *, expires_in: int = 300, **overrides: Any) -> str:
    """Craft a signed JWT directly, bypassing the service (for negative paths)."""
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(uuid.uuid4()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now - timedelta(seconds=600),
        "exp": now + timedelta(seconds=expires_in),
        "jti": uuid.uuid4().hex,
        "type": token_type,
        "ver": 0,
    }
    payload.update(overrides)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


async def _get_user(session: AsyncSession, email: str) -> User:
    result = await session.exec(select(User).where(User.email == email))
    return result.one()


async def test_register_returns_public_user(client: AsyncClient) -> None:
    response = await client.post(
        f"{API}/auth/register",
        json={"email": "alice@example.com", "password": "supersecret123", "full_name": "Alice"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "alice@example.com"
    assert "hashed_password" not in body


async def test_login_and_me(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "eve@example.com", "supersecret123")
    assert tokens["token_type"] == "bearer"

    me = await client.get(
        f"{API}/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == "eve@example.com"


async def test_duplicate_email_conflicts(client: AsyncClient) -> None:
    body = {"email": "bob@example.com", "password": "supersecret123"}
    assert (await client.post(f"{API}/auth/register", json=body)).status_code == 201
    assert (await client.post(f"{API}/auth/register", json=body)).status_code == 409


async def test_login_with_wrong_password(client: AsyncClient) -> None:
    await client.post(
        f"{API}/auth/register",
        json={"email": "dave@example.com", "password": "supersecret123"},
    )
    response = await client.post(
        f"{API}/auth/login",
        data={"username": "dave@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401


async def test_refresh_returns_new_tokens(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "carol@example.com", "supersecret123")
    refresh = await client.post(
        f"{API}/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh.status_code == 200
    assert refresh.json()["access_token"]


async def test_protected_route_requires_token(client: AsyncClient) -> None:
    response = await client.get(f"{API}/{{ cookiecutter.first_entity }}s")
    assert response.status_code == 401


def test_email_token_round_trip() -> None:
    user_id = uuid.uuid4()
    token = create_email_token(user_id, "password_reset")
    payload = decode_token(token)
    assert payload["sub"] == str(user_id)
    assert payload["type"] == "password_reset"
    assert payload["exp"] > payload["iat"]


async def test_email_token_is_not_an_access_token(client: AsyncClient) -> None:
    token = create_email_token(uuid.uuid4(), "password_reset")
    response = await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


async def test_me_rejects_non_access_tokens(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "kate@example.com", "supersecret123")
    response = await client.get(
        f"{API}/auth/me",
        headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
    )
    assert response.status_code == 401


async def test_forgot_password_then_reset(
    client: AsyncClient, outbox: CapturingEmailBackend
) -> None:
    await client.post(
        f"{API}/auth/register",
        json={"email": "grace@example.com", "password": "supersecret123"},
    )
    old_session = await client.post(
        f"{API}/auth/login",
        data={"username": "grace@example.com", "password": "supersecret123"},
    )
    old_tokens = old_session.json()
    response = await client.post(f"{API}/auth/forgot-password", json={"email": "grace@example.com"})
    assert response.status_code == 202
    assert len(outbox.messages) == 1
    assert outbox.messages[0].to == "grace@example.com"

    token = _token_from(outbox.messages[0])
    reset = await client.post(
        f"{API}/auth/reset-password",
        json={"token": token, "new_password": "newsecret12345"},
    )
    assert reset.status_code == 200

    replay = await client.post(
        f"{API}/auth/reset-password",
        json={"token": token, "new_password": "attacker-chosen-password"},
    )
    assert replay.status_code == 401
    assert (
        await client.get(
            f"{API}/auth/me",
            headers={"Authorization": f"Bearer {old_tokens['access_token']}"},
        )
    ).status_code == 401
    assert (
        await client.post(
            f"{API}/auth/refresh",
            json={"refresh_token": old_tokens["refresh_token"]},
        )
    ).status_code == 401

    old = await client.post(
        f"{API}/auth/login",
        data={"username": "grace@example.com", "password": "supersecret123"},
    )
    assert old.status_code == 401
    new = await client.post(
        f"{API}/auth/login",
        data={"username": "grace@example.com", "password": "newsecret12345"},
    )
    assert new.status_code == 200


async def test_forgot_password_discloses_nothing_for_unknown_email(
    client: AsyncClient, outbox: CapturingEmailBackend
) -> None:
    response = await client.post(f"{API}/auth/forgot-password", json={"email": "ghost@example.com"})
    assert response.status_code == 202
    assert outbox.messages == []


async def test_reset_password_rejects_wrong_token_type(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "henry@example.com", "supersecret123")
    response = await client.post(
        f"{API}/auth/reset-password",
        json={"token": tokens["access_token"], "new_password": "newsecret12345"},
    )
    assert response.status_code == 401


async def test_reset_password_rejects_garbage_token(client: AsyncClient) -> None:
    response = await client.post(
        f"{API}/auth/reset-password",
        json={"token": "not-a-token", "new_password": "newsecret12345"},
    )
    assert response.status_code == 401


async def test_email_verification_flow(
    client: AsyncClient,
    outbox: CapturingEmailBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "require_email_verification", True)

    register = await client.post(
        f"{API}/auth/register",
        json={"email": "ivy@example.com", "password": "supersecret123"},
    )
    assert register.status_code == 201
    assert register.json()["is_verified"] is False
    assert len(outbox.messages) == 1
    assert outbox.messages[0].to == "ivy@example.com"

    blocked = await client.post(
        f"{API}/auth/login",
        data={"username": "ivy@example.com", "password": "supersecret123"},
    )
    assert blocked.status_code == 401

    token = _token_from(outbox.messages[0])
    verify = await client.post(f"{API}/auth/verify-email", json={"token": token})
    assert verify.status_code == 200

    login = await client.post(
        f"{API}/auth/login",
        data={"username": "ivy@example.com", "password": "supersecret123"},
    )
    assert login.status_code == 200


async def test_register_skips_verification_email_when_not_required(
    client: AsyncClient, outbox: CapturingEmailBackend
) -> None:
    response = await client.post(
        f"{API}/auth/register",
        json={"email": "liam@example.com", "password": "supersecret123"},
    )
    assert response.status_code == 201
    assert outbox.messages == []


async def test_verification_email_failure_does_not_rollback_registration(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "require_email_verification", True)
    monkeypatch.setattr(auth_service, "get_email_backend", FailingEmailBackend)

    response = await client.post(
        f"{API}/auth/register",
        json={"email": "delivery-failure@example.com", "password": "supersecret123"},
    )

    assert response.status_code == 201
    assert (await _get_user(session, "delivery-failure@example.com")).email == (
        "delivery-failure@example.com"
    )
    login = await client.post(
        f"{API}/auth/login",
        data={"username": "delivery-failure@example.com", "password": "supersecret123"},
    )
    assert login.status_code == 401  # persisted, but correctly blocked until verified


async def test_resend_verification_is_non_enumerating(
    client: AsyncClient,
    outbox: CapturingEmailBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "require_email_verification", True)
    await client.post(
        f"{API}/auth/register",
        json={"email": "resend@example.com", "password": "supersecret123"},
    )
    outbox.messages.clear()

    known = await client.post(
        f"{API}/auth/resend-verification", json={"email": "resend@example.com"}
    )
    assert known.status_code == 202
    assert len(outbox.messages) == 1

    outbox.messages.clear()
    unknown = await client.post(
        f"{API}/auth/resend-verification", json={"email": "unknown@example.com"}
    )
    assert unknown.status_code == 202
    assert unknown.json() == known.json()
    assert outbox.messages == []


# --- Negative paths: token verification -------------------------------------


async def test_expired_access_token_is_rejected(client: AsyncClient) -> None:
    token = _make_token("access", expires_in=-60)
    response = await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


async def test_tampered_signature_is_rejected(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "mallet@example.com", "supersecret123")
    token = tokens["access_token"]
    tampered = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
    response = await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tampered}"})
    assert response.status_code == 401


async def test_token_without_audience_is_rejected(client: AsyncClient) -> None:
    """A token from another service sharing SECRET_KEY (no aud/iss) must not pass."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "jti": uuid.uuid4().hex,
        "type": "access",
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
    response = await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_token_missing_required_claim_rejected() -> None:
    payload = {  # no jti/type/iss/aud -> must not verify
        "sub": "someone",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
        "iat": datetime.now(UTC),
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
    with pytest.raises(jwt.MissingRequiredClaimError):
        decode_token(token)


async def test_refresh_rejects_access_token(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "tara@example.com", "supersecret123")
    response = await client.post(
        f"{API}/auth/refresh",
        json={"refresh_token": tokens["access_token"]},
    )
    assert response.status_code == 401


async def test_inactive_user_is_rejected(client: AsyncClient, session: AsyncSession) -> None:
    tokens = await _register_and_login(client, "mallory@example.com", "supersecret123")
    user = await _get_user(session, "mallory@example.com")
    user.is_active = False
    session.add(user)
    await session.commit()

    me = await client.get(
        f"{API}/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me.status_code == 403
    login = await client.post(
        f"{API}/auth/login",
        data={"username": "mallory@example.com", "password": "supersecret123"},
    )
    assert login.status_code == 401
    refresh = await client.post(
        f"{API}/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh.status_code == 401


# --- Refresh rotation, logout and reuse detection ----------------------------


async def test_logout_revokes_refresh_family(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "quinn@example.com", "supersecret123")
    logout = await client.post(
        f"{API}/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert logout.status_code == 200
    refresh = await client.post(
        f"{API}/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh.status_code == 401


async def test_reused_rotated_refresh_token_burns_family(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "ruth@example.com", "supersecret123")
    first = await client.post(
        f"{API}/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert first.status_code == 200
    rotated = first.json()

    replay = await client.post(
        f"{API}/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert replay.status_code == 401

    # Reuse revokes the whole family: the legitimate successor is dead too.
    successor = await client.post(
        f"{API}/auth/refresh",
        json={"refresh_token": rotated["refresh_token"]},
    )
    assert successor.status_code == 401


async def test_concurrent_refresh_allows_only_one_rotation(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "race@example.com", "supersecret123")
    first, second = await asyncio.gather(
        client.post(
            f"{API}/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        ),
        client.post(
            f"{API}/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        ),
    )
    assert sorted((first.status_code, second.status_code)) == [200, 401]


# --- Account lifecycle: password change, export, erasure ---------------------


async def test_change_password_flow(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "nina@example.com", "supersecret123")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    wrong = await client.post(
        f"{API}/auth/password",
        json={"current_password": "not-my-password", "new_password": "newsecret12345"},
        headers=headers,
    )
    assert wrong.status_code == 403

    ok = await client.post(
        f"{API}/auth/password",
        json={"current_password": "supersecret123", "new_password": "newsecret12345"},
        headers=headers,
    )
    assert ok.status_code == 200

    assert (await client.get(f"{API}/auth/me", headers=headers)).status_code == 401
    assert (
        await client.post(
            f"{API}/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
    ).status_code == 401

    old = await client.post(
        f"{API}/auth/login",
        data={"username": "nina@example.com", "password": "supersecret123"},
    )
    assert old.status_code == 401
    new = await client.post(
        f"{API}/auth/login",
        data={"username": "nina@example.com", "password": "newsecret12345"},
    )
    assert new.status_code == 200


async def test_export_returns_stored_data(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "paula@example.com", "supersecret123")
    response = await client.get(
        f"{API}/auth/me/export",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "paula@example.com"
    assert "hashed_password" not in body["user"]
    assert body["exported_at"]


async def test_delete_me_erases_account(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "olga@example.com", "supersecret123")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    delete = await client.delete(f"{API}/auth/me", headers=headers)
    assert delete.status_code == 204

    assert (await client.get(f"{API}/auth/me", headers=headers)).status_code == 401
    login = await client.post(
        f"{API}/auth/login",
        data={"username": "olga@example.com", "password": "supersecret123"},
    )
    assert login.status_code == 401
    refresh = await client.post(
        f"{API}/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh.status_code == 401


# --- Password hash lifecycle --------------------------------------------------


async def test_login_rehashes_outdated_password_hash(
    client: AsyncClient, session: AsyncSession
) -> None:
    await client.post(
        f"{API}/auth/register",
        json={"email": "sam@example.com", "password": "supersecret123"},
    )
    # Downgrade the stored hash to deliberately weak Argon2 parameters.
    weak_hasher = PasswordHash((Argon2Hasher(time_cost=1, memory_cost=8, parallelism=1),))
    weak_hash = weak_hasher.hash("supersecret123")
    user = await _get_user(session, "sam@example.com")
    user.hashed_password = weak_hash
    session.add(user)
    await session.commit()

    login = await client.post(
        f"{API}/auth/login",
        data={"username": "sam@example.com", "password": "supersecret123"},
    )
    assert login.status_code == 200

    await session.refresh(user)
    assert user.hashed_password != weak_hash  # transparently rehashed on login


# --- Superuser dependency and bootstrap ---------------------------------------


async def test_superuser_dependency_requires_superuser() -> None:
    root = User(email="root@example.com", hashed_password="x", is_superuser=True)
    assert await get_current_superuser(root) is root
    with pytest.raises(ForbiddenError):
        await get_current_superuser(User(email="pleb@example.com", hashed_password="x"))


async def test_first_superuser_bootstrap_is_idempotent(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bootstrap, "async_session_factory", session_factory)
    monkeypatch.setattr(settings, "first_superuser_email", "admin@example.com")
    monkeypatch.setattr(settings, "first_superuser_password", "adminsecret123")

    await bootstrap.ensure_first_superuser()
    await bootstrap.ensure_first_superuser()  # second run must be a no-op

    async with session_factory() as check_session:
        user = await _get_user(check_session, "admin@example.com")
    assert user.is_superuser
    assert user.is_verified
