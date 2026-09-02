"""Refresh-token store backing rotation, revocation and reuse detection.

Rotation model (RFC 6819 refresh-token rotation): every login starts a token
*family*; each refresh invalidates the presented ``jti`` and records its
successor. A signature-valid token whose ``jti`` was already rotated is
treated as stolen and burns the whole family, logging out the legitimate
session too.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

{% if cookiecutter.use_redis == "yes" -%}
import redis.asyncio as redis
{%- else -%}
from sqlalchemy import update
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from {{ cookiecutter.package_name }}.domains.auth.models import RefreshToken
{%- endif %}

# "ok": jti is current — caller may rotate. "reused": jti was already rotated
# or revoked — caller must burn the family. "unknown": never issued, expired
# or family already revoked.
TokenState = Literal["ok", "reused", "unknown"]

{% if cookiecutter.use_redis == "yes" %}
class RefreshTokenStore:
    """Redis-backed store: one key per family holding the currently valid jti.

    The key's TTL tracks the newest refresh token, so stale families expire on
    their own. A missing key cannot distinguish "revoked" from "expired", but
    both answer the same way: reject.
    """

    def __init__(self, client: redis.Redis) -> None:
        self._redis = client

    @staticmethod
    def _key(family: str) -> str:
        return f"auth:refresh:{family}"

    async def store(self, *, jti: str, family: str, user_id: UUID, expires_at: datetime) -> None:
        """Record ``jti`` as the family's current token until ``expires_at``."""
        del user_id  # tracked by the DB-backed variant; the token itself carries `sub`
        ttl = max(int((expires_at - datetime.now(UTC)).total_seconds()), 1)
        await self._redis.set(self._key(family), jti, ex=ttl)

    async def rotate(
        self,
        *,
        jti: str,
        new_jti: str,
        family: str,
        user_id: UUID,
        expires_at: datetime,
    ) -> TokenState:
        """Atomically consume ``jti`` and install ``new_jti`` as its successor."""
        del user_id  # the signed token carries `sub`; Redis stores one key per family
        ttl = max(int((expires_at - datetime.now(UTC)).total_seconds()), 1)
        script = """
        local current = redis.call('GET', KEYS[1])
        if not current then return 0 end
        if current ~= ARGV[1] then return -1 end
        redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
        return 1
        """
        verdict = int(
            await self._redis.eval(
                script,
                1,
                self._key(family),
                jti,
                new_jti,
                ttl,
            )
        )
        if verdict == 1:
            return "ok"
        if verdict == -1:
            return "reused"
        return "unknown"

    async def revoke_family(self, family: str) -> None:
        await self._redis.delete(self._key(family))
{%- else %}
class RefreshTokenStore:
    """Database-backed store: one ``refresh_tokens`` row per issued jti.

    Rotated rows stay behind with ``revoked_at`` set so reuse of an old token
    is distinguishable from a token that never existed. Expired rows for a
    user are purged whenever that user is issued a new token.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def store(self, *, jti: str, family: str, user_id: UUID, expires_at: datetime) -> None:
        """Record ``jti`` as issued and purge the user's expired rows."""
        result = await self.session.exec(
            select(RefreshToken)
            .where(col(RefreshToken.user_id) == user_id)
            .where(col(RefreshToken.expires_at) <= datetime.now(UTC))
        )
        for stale in result.all():
            await self.session.delete(stale)
        self.session.add(
            RefreshToken(jti=jti, family=family, user_id=user_id, expires_at=expires_at)
        )
        await self.session.flush()

    async def rotate(
        self,
        *,
        jti: str,
        new_jti: str,
        family: str,
        user_id: UUID,
        expires_at: datetime,
    ) -> TokenState:
        """Atomically consume ``jti`` and insert its successor in this transaction."""
        now = datetime.now(UTC)
        result = await self.session.exec(
            update(RefreshToken)
            .where(col(RefreshToken.jti) == jti)
            .where(col(RefreshToken.family) == family)
            .where(col(RefreshToken.revoked_at).is_(None))
            .where(col(RefreshToken.expires_at) > now)
            .values(revoked_at=now)
            .returning(col(RefreshToken.jti))
        )
        if result.one_or_none() is None:
            token = await self.session.get(RefreshToken, jti, populate_existing=True)
            if token is not None and token.family == family and token.revoked_at is not None:
                return "reused"
            return "unknown"
        self.session.add(
            RefreshToken(
                jti=new_jti,
                family=family,
                user_id=user_id,
                expires_at=expires_at,
            )
        )
        await self.session.flush()
        return "ok"

    async def revoke_family(self, family: str) -> None:
        result = await self.session.exec(
            select(RefreshToken)
            .where(col(RefreshToken.family) == family)
            .where(col(RefreshToken.revoked_at).is_(None))
        )
        now = datetime.now(UTC)
        for token in result.all():
            token.revoked_at = now
            self.session.add(token)
        # Commit immediately: revocation is a security decision that must
        # survive the request-scoped rollback triggered by the 401 the caller
        # raises right after detecting reuse.
        await self.session.commit()
{%- endif %}
