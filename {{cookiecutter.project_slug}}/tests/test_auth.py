"""Tests for the authentication endpoints and email flows."""

from __future__ import annotations

import re
import uuid

import pytest
from httpx import AsyncClient

from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.core.email import EmailMessage
from {{ cookiecutter.package_name }}.core.security import decode_token
from {{ cookiecutter.package_name }}.domains.auth import service as auth_service

API = settings.api_v1_prefix


class CapturingEmailBackend:
    """Collects rendered emails instead of delivering them."""

    def __init__(self) -> None:
        self.messages: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        self.messages.append(message)


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


async def _register_and_login(client: AsyncClient, email: str, secret: str) -> dict[str, str]:
    await client.post(f"{API}/auth/register", json={"email": email, "password": secret})
    response = await client.post(f"{API}/auth/login", data={"username": email, "password": secret})
    return response.json()


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
    token = auth_service.create_email_token(user_id, "password_reset")
    payload = decode_token(token)
    assert payload["sub"] == str(user_id)
    assert payload["type"] == "password_reset"
    assert payload["exp"] > payload["iat"]


async def test_email_token_is_not_an_access_token(client: AsyncClient) -> None:
    token = auth_service.create_email_token(uuid.uuid4(), "password_reset")
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
