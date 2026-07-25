"""Bearer-token verification for the MCP endpoint.

Verifies the same HS256 JWTs the HTTP API mints, so an agent authenticates
against ``/mcp`` with a token obtained from ``POST /api/v1/auth/login``.
"""

from __future__ import annotations

from fastmcp.server.auth import AccessToken
from fastmcp.server.auth.providers.jwt import JWTVerifier

from {{ cookiecutter.package_name }}.core.config import settings


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
