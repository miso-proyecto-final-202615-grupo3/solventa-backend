import uuid
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import Base

Model = TypeVar("Model", bound=Base)


class SqlAlchemyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def guardar(self, model: Model) -> Model:
        self.session.add(model)
        await self.session.flush()
        return model

    async def obtener_por_id(self, model_type: type[Model], entity_id: uuid.UUID) -> Model | None:
        return await self.session.get(model_type, entity_id)
