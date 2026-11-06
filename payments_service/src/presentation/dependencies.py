from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import SessionLocal
from src.domain.pagos.repositories import PagoRepository
from src.infrastructure.persistence.pagos_repository_impl import SqlAlchemyPagoRepository


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


def get_pago_repository(db: AsyncSession = Depends(get_db)) -> PagoRepository:
    return SqlAlchemyPagoRepository(db)
