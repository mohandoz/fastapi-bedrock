"""Bearer-token verification for the MCP endpoint.

Verifies the same HS256 JWTs the HTTP API mints, so an agent authenticates
against ``/mcp`` with a token obtained from ``POST /api/v1/auth/login``.
"""

from __future__ import annotations

from uuid import UUID

from fastmcp.server.auth import AccessToken
from fastmcp.server.auth.providers.jwt import JWTVerifier

from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.core.database import async_session_factory
from {{ cookiecutter.package_name }}.domains.auth.repository import UserRepository


class AccessTokenVerifier(JWTVerifier):
    """Accept only *access* tokens minted by this service's auth domain.

    The base verifier already checks signature, expiry, issuer and audience;
    this subclass additionally rejects refresh/email tokens (``type`` claim),
    mirroring ``domains.auth.dependencies.get_current_user``.
    """

    async def verify_token(self, token: str) -> AccessToken | None:
        access = await super().verify_token(token)
        if access is None or access.claims.get("type") != "access":
            return None
        subject = access.claims.get("sub")
        version = access.claims.get("ver")
        if not isinstance(subject, str) or not isinstance(version, int):
            return None
        try:
            user_id = UUID(subject)
        except ValueError:
            return None
        # Signature validity is insufficient for account authorization: match
        # the REST dependency by rejecting deleted, inactive and pre-password-
        # change sessions on every MCP authentication.
        async with async_session_factory() as session:
            user = await UserRepository(session).get(user_id)
            if user is None or not user.is_active or user.auth_version != version:
                return None
        return access


def build_token_verifier() -> AccessTokenVerifier:
    """Verify MCP bearer tokens against the same JWT config as the HTTP API."""
    return AccessTokenVerifier(
        # `public_key` doubles as the shared secret for HS* algorithms.
        public_key=settings.secret_key,
        algorithm=settings.algorithm,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
    )
