from collections.abc import AsyncGenerator, Callable
from datetime import UTC, datetime, timedelta

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.almacen_evidencias import AlmacenEvidenciasPort, AlmacenNoDisponible
from src.application.ports.polizas import PolizasPort
from src.application.use_cases.consultar_siniestro_use_case import ConsultarSiniestroUseCase
from src.application.use_cases.evidencias_use_cases import (
    ConfirmarCargaEvidenciaUseCase,
    ConsultarDetalleSiniestroUseCase,
    ObtenerDescargaEvidenciaUseCase,
    RegistrarUbicacionUseCase,
    SolicitarCargaEvidenciaUseCase,
)
from src.application.use_cases.listar_polizas_elegibles_use_case import ListarPolizasElegiblesUseCase
from src.application.use_cases.listar_siniestros_use_case import ListarSiniestrosUseCase
from src.application.use_cases.reportar_siniestro_use_case import ReportarSiniestroUseCase
from src.core.config import settings
from src.core.database import SessionLocal
from src.domain.siniestros.catalogo import CatalogoTiposSiniestro
from src.domain.siniestros.errores import ServicioNoDisponible
from src.domain.siniestros.politica_evidencias import MB, LimitesEvidencia, PoliticaEvidencias
from src.infrastructure.gateways.polizas_factory import crear_polizas_port
from src.infrastructure.persistence.catalogo_tipos_siniestro_impl import SqlAlchemyCatalogoTiposSiniestro
from src.infrastructure.storage.factory import crear_almacen
from src.domain.siniestros.repositories import (
    ActivacionParametricaRepository,
    ActivacionPolizaRepository,
    EventoExternoRepository,
    EvidenciaRepository,
    IndemnizacionRepository,
    SiniestroRepository,
)
from src.infrastructure.persistence.siniestros_repository_impl import (
    SqlAlchemyActivacionParametricaRepository,
    SqlAlchemyActivacionPolizaRepository,
    SqlAlchemyEventoExternoRepository,
    SqlAlchemyEvidenciaRepository,
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


# --- HU4.1.2 · Evidencias y ubicación ---------------------------------------------------------

def get_evidencia_repository(db: AsyncSession = Depends(get_db)) -> EvidenciaRepository:
    return SqlAlchemyEvidenciaRepository(db)


def get_almacen() -> AlmacenEvidenciasPort:
    try:
        return crear_almacen(settings)
    except AlmacenNoDisponible as exc:
        raise ServicioNoDisponible() from exc


def get_politica() -> PoliticaEvidencias:
    return PoliticaEvidencias(
        LimitesEvidencia(foto_max_bytes=settings.FOTO_MAX_MB * MB, video_max_bytes=settings.VIDEO_MAX_MB * MB)
    )


def get_solicitar_carga_use_case(
    db: AsyncSession = Depends(get_db),
    siniestros: SiniestroRepository = Depends(get_siniestro_repository),
    evidencias: EvidenciaRepository = Depends(get_evidencia_repository),
    catalogo: CatalogoTiposSiniestro = Depends(get_catalogo),
    almacen: AlmacenEvidenciasPort = Depends(get_almacen),
    politica: PoliticaEvidencias = Depends(get_politica),
    reloj: Callable[[], datetime] = Depends(get_reloj),
) -> SolicitarCargaEvidenciaUseCase:
    return SolicitarCargaEvidenciaUseCase(
        db, siniestros, evidencias, catalogo, almacen, politica, reloj, settings.EVIDENCIAS_PREFIX
    )


def get_confirmar_carga_use_case(
    db: AsyncSession = Depends(get_db),
    siniestros: SiniestroRepository = Depends(get_siniestro_repository),
    evidencias: EvidenciaRepository = Depends(get_evidencia_repository),
    almacen: AlmacenEvidenciasPort = Depends(get_almacen),
    politica: PoliticaEvidencias = Depends(get_politica),
    reloj: Callable[[], datetime] = Depends(get_reloj),
) -> ConfirmarCargaEvidenciaUseCase:
    return ConfirmarCargaEvidenciaUseCase(db, siniestros, evidencias, almacen, politica, reloj)


def get_registrar_ubicacion_use_case(
    db: AsyncSession = Depends(get_db),
    siniestros: SiniestroRepository = Depends(get_siniestro_repository),
    politica: PoliticaEvidencias = Depends(get_politica),
    reloj: Callable[[], datetime] = Depends(get_reloj),
) -> RegistrarUbicacionUseCase:
    return RegistrarUbicacionUseCase(db, siniestros, politica, reloj)


def get_consultar_detalle_siniestro_use_case(
    siniestros: SiniestroRepository = Depends(get_siniestro_repository),
    evidencias: EvidenciaRepository = Depends(get_evidencia_repository),
    reloj: Callable[[], datetime] = Depends(get_reloj),
) -> ConsultarDetalleSiniestroUseCase:
    return ConsultarDetalleSiniestroUseCase(siniestros, evidencias, reloj)


# --- HU4.2.1 · Consultar siniestros y ver evidencias ----------------------------------------

def get_listar_siniestros_use_case(
    repo: SiniestroRepository = Depends(get_siniestro_repository),
) -> ListarSiniestrosUseCase:
    return ListarSiniestrosUseCase(repo)


def get_obtener_descarga_evidencia_use_case(
    siniestros: SiniestroRepository = Depends(get_siniestro_repository),
    evidencias: EvidenciaRepository = Depends(get_evidencia_repository),
    almacen: AlmacenEvidenciasPort = Depends(get_almacen),
) -> ObtenerDescargaEvidenciaUseCase:
    return ObtenerDescargaEvidenciaUseCase(
        siniestros, evidencias, almacen, timedelta(seconds=settings.EVIDENCIAS_DESCARGA_TTL_SECONDS)
    )
