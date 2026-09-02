"""User repository."""

from __future__ import annotations

from sqlalchemy import update
from sqlmodel import col, select

from {{ cookiecutter.package_name }}.core.repository import BaseRepository
from {{ cookiecutter.package_name }}.domains.auth.models import User


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.exec(select(User).where(User.email == email))
        return result.first()

    async def update_password_if_version(
        self,
        user: User,
        *,
        expected_version: int,
        hashed_password: str,
    ) -> bool:
        """Replace the password once and invalidate tokens issued under its old version."""
        result = await self.session.exec(
            update(User)
            .where(col(User.id) == user.id)
            .where(col(User.auth_version) == expected_version)
            .values(
                hashed_password=hashed_password,
                auth_version=expected_version + 1,
            )
            .returning(col(User.id))
        )
        return result.one_or_none() is not None
