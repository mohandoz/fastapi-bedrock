"""Tests for the authentication endpoints."""

from __future__ import annotations

from httpx import AsyncClient

from {{ cookiecutter.package_name }}.core.config import settings

API = settings.api_v1_prefix


async def _register_and_login(client: AsyncClient, email: str, secret: str) -> dict[str, str]:
    await client.post(f"{API}/auth/register", json={"email": email, "password": secret})
    response = await client.post(
        f"{API}/auth/login", data={"username": email, "password": secret}
    )
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
