from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import SessionLocal
from src.domain.polizas.repositories import PolizaRepository
from src.infrastructure.persistence.poliza_repository_impl import (
    SqlAlchemyPolizaRepository,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


def get_poliza_repository(
    db: AsyncSession = Depends(get_db),
) -> PolizaRepository:
    return SqlAlchemyPolizaRepository(db)
