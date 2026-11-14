from collections.abc import AsyncGenerator, Callable
from datetime import UTC, datetime

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.polizas import PolizasPort
from src.application.use_cases.consultar_siniestro_use_case import ConsultarSiniestroUseCase
from src.application.use_cases.listar_polizas_elegibles_use_case import ListarPolizasElegiblesUseCase
from src.application.use_cases.reportar_siniestro_use_case import ReportarSiniestroUseCase
from src.core.config import settings
from src.core.database import SessionLocal
from src.domain.siniestros.catalogo import CatalogoTiposSiniestro
from src.infrastructure.gateways.polizas_factory import crear_polizas_port
from src.infrastructure.persistence.catalogo_tipos_siniestro_impl import SqlAlchemyCatalogoTiposSiniestro
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


# --- HU4.1.1 · Registrar un siniestro ---------------------------------------------------------

def get_reloj() -> Callable[[], datetime]:
    return lambda: datetime.now(UTC)


def get_catalogo(db: AsyncSession = Depends(get_db)) -> CatalogoTiposSiniestro:
    return SqlAlchemyCatalogoTiposSiniestro(db)


async def get_polizas_port() -> AsyncGenerator[PolizasPort, None]:
    port = crear_polizas_port(settings)
    try:
        yield port
    finally:
        await port.aclose()


def _estados_elegibles() -> list[str]:
    return settings.ESTADOS_POLIZA_ELEGIBLES.split(",")


def get_listar_polizas_elegibles_use_case(
    polizas: PolizasPort = Depends(get_polizas_port),
    catalogo: CatalogoTiposSiniestro = Depends(get_catalogo),
    reloj: Callable[[], datetime] = Depends(get_reloj),
) -> ListarPolizasElegiblesUseCase:
    return ListarPolizasElegiblesUseCase(polizas, catalogo, reloj, _estados_elegibles())


def get_reportar_siniestro_use_case(
    db: AsyncSession = Depends(get_db),
    repo: SiniestroRepository = Depends(get_siniestro_repository),
    polizas: PolizasPort = Depends(get_polizas_port),
    catalogo: CatalogoTiposSiniestro = Depends(get_catalogo),
    reloj: Callable[[], datetime] = Depends(get_reloj),
) -> ReportarSiniestroUseCase:
    return ReportarSiniestroUseCase(db, repo, polizas, catalogo, reloj, _estados_elegibles())


def get_consultar_siniestro_use_case(
    repo: SiniestroRepository = Depends(get_siniestro_repository),
) -> ConsultarSiniestroUseCase:
    return ConsultarSiniestroUseCase(repo)
