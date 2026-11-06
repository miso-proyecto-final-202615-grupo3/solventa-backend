from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import SessionLocal
from src.domain.siniestros.repositories import (
    ActivacionParametricaRepository,
    ActivacionPolizaRepository,
    EventoExternoRepository,
    IndemnizacionRepository,
    SiniestroRepository,
)
from src.infrastructure.persistence.siniestros_repository_impl import (
    SqlAlchemyActivacionParametricaRepository,
    SqlAlchemyActivacionPolizaRepository,
    SqlAlchemyEventoExternoRepository,
    SqlAlchemyIndemnizacionRepository,
    SqlAlchemySiniestroRepository,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


def get_evento_externo_repository(db: AsyncSession = Depends(get_db)) -> EventoExternoRepository:
    return SqlAlchemyEventoExternoRepository(db)


def get_activacion_parametrica_repository(
    db: AsyncSession = Depends(get_db),
) -> ActivacionParametricaRepository:
    return SqlAlchemyActivacionParametricaRepository(db)


def get_activacion_poliza_repository(
    db: AsyncSession = Depends(get_db),
) -> ActivacionPolizaRepository:
    return SqlAlchemyActivacionPolizaRepository(db)


def get_siniestro_repository(db: AsyncSession = Depends(get_db)) -> SiniestroRepository:
    return SqlAlchemySiniestroRepository(db)


def get_indemnizacion_repository(db: AsyncSession = Depends(get_db)) -> IndemnizacionRepository:
    return SqlAlchemyIndemnizacionRepository(db)
