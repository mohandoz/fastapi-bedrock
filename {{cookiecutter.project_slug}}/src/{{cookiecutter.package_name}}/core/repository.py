"""Generic asynchronous repository built on top of SQLModel sessions."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession


class BaseRepository[ModelT: SQLModel]:
    """CRUD operations shared by every concrete repository.

    Subclasses only need to set the ``model`` class attribute::

        class ItemRepository(BaseRepository[Item]):
            model = Item
    """

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, entity_id: UUID) -> ModelT | None:
        return await self.session.get(self.model, entity_id)

    async def list(self, *, offset: int = 0, limit: int = 100) -> Sequence[ModelT]:
        result = await self.session.exec(select(self.model).offset(offset).limit(limit))
        return result.all()

    async def add(self, instance: ModelT) -> ModelT:
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update(self, instance: ModelT, data: dict[str, Any]) -> ModelT:
        instance.sqlmodel_update(data)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, instance: ModelT) -> None:
        await self.session.delete(instance)
        await self.session.flush()
