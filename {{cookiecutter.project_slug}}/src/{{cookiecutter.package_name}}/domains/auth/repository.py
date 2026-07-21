"""User repository."""

from __future__ import annotations

from sqlmodel import select

from {{ cookiecutter.package_name }}.core.repository import BaseRepository
from {{ cookiecutter.package_name }}.domains.auth.models import User


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.exec(select(User).where(User.email == email))
        return result.first()
