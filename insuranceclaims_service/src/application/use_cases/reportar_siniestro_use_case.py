import hashlib
import json
import logging
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.polizas import PolizasNoDisponibles, PolizasPort
from src.application.use_cases.listar_polizas_elegibles_use_case import (
    dia_en_vigencia,
    poliza_en_estado_elegible,
)
from src.domain.siniestros.catalogo import CatalogoTiposSiniestro
from src.domain.siniestros.entities import Siniestro
from src.domain.siniestros.enums import CanalReporte, EstadoSiniestro
from src.domain.siniestros.errores import (
    FechaFueraDeVigencia,
    FechaInvalida,
    IdempotenciaConflicto,
    PolizaNoEncontrada,
    PolizaNoVigente,
    ServicioNoDisponible,
    TipoNoPermitido,
)
from src.domain.siniestros.folio import generar_numero
from src.domain.siniestros.repositories import SiniestroRepository

logger = logging.getLogger(__name__)

TOLERANCIA_RELOJ = timedelta(minutes=5)


@dataclass(frozen=True)
class ReporteSiniestroCmd:
    cliente_id: uuid.UUID
    clave_idempotencia: str
    poliza_id: uuid.UUID
    tipo: str
    descripcion: str
    ocurrido_en: datetime  # con zona horaria


@dataclass(frozen=True)
class ResultadoReporte:
    siniestro: Siniestro
    repetido: bool


def huella_de(cmd: ReporteSiniestroCmd) -> str:
    """SHA-256 del contenido del reporte: detecta reusar la clave con otros datos."""
    contenido = {
        "cliente_id": str(cmd.cliente_id),
        "poliza_id": str(cmd.poliza_id),
        "tipo": cmd.tipo,
        "descripcion": cmd.descripcion,
        "ocurrido_en": cmd.ocurrido_en.astimezone(UTC).isoformat(),
    }
    return hashlib.sha256(json.dumps(contenido, sort_keys=True).encode()).hexdigest()


class ReportarSiniestroUseCase:
    """Crea el siniestro asistido en estado REPORTADO (HU4.1.1). Idempotente por `clave_idempotencia`."""

    def __init__(
        self,
        session: AsyncSession,
        repo: SiniestroRepository,
        polizas: PolizasPort,
        catalogo: CatalogoTiposSiniestro,
        reloj: Callable[[], datetime],
        estados_elegibles: Iterable[str],
    ) -> None:
        self.session = session
        self.repo = repo
        self.polizas = polizas
        self.catalogo = catalogo
        self.reloj = reloj
        self.estados_elegibles = tuple(estados_elegibles)

    async def ejecutar(self, cmd: ReporteSiniestroCmd, correlation_id: str) -> ResultadoReporte:
        huella = huella_de(cmd)
        repetido = await self._repetido(cmd, huella)
        if repetido is not None:
            return repetido

        ahora = self.reloj()
        if cmd.ocurrido_en > ahora + TOLERANCIA_RELOJ:
            raise FechaInvalida()

        try:
            poliza = await self.polizas.obtener(cmd.poliza_id, cmd.cliente_id, correlation_id)
        except PolizasNoDisponibles as exc:
            raise ServicioNoDisponible() from exc
        if poliza is None or poliza.cliente_id != cmd.cliente_id:
            raise PolizaNoEncontrada()
        if not poliza_en_estado_elegible(poliza, self.estados_elegibles):
            raise PolizaNoVigente()
        # El día del evento en la zona horaria del cliente.
        if not dia_en_vigencia(poliza, cmd.ocurrido_en.date()):
            raise FechaFueraDeVigencia()
        if await self.catalogo.obtener(poliza.producto_codigo, cmd.tipo) is None:
            raise TipoNoPermitido()

        for intento in range(2):
            siniestro = Siniestro(
                poliza_id=poliza.poliza_id,
                tipo=cmd.tipo,
                estado=EstadoSiniestro.REPORTADO.value,
                clave_idempotencia=cmd.clave_idempotencia,
                ocurrido_en=cmd.ocurrido_en.astimezone(UTC),
                reportado_en=ahora,
                cliente_id=cmd.cliente_id,
                canal=CanalReporte.MOVIL.value,
                descripcion=cmd.descripcion,
                poliza_numero=poliza.numero,
                producto_codigo=poliza.producto_codigo,
                huella_solicitud=huella,
            )
            siniestro.numero = generar_numero(siniestro.siniestro_id, ahora)
            try:
                await self.repo.guardar(siniestro)
                await self.session.commit()
            except IntegrityError:
                await self.session.rollback()
                # Otra solicitud con la misma clave ganó la carrera: se responde lo que ella creó.
                repetido = await self._repetido(cmd, huella)
                if repetido is not None:
                    return repetido
                if intento == 1:
                    raise
                continue  # choque del folio: se reintenta una vez con otro UUID
            logger.info(
                "siniestro_reportado numero=%s canal=%s correlation_id=%s",
                siniestro.numero, siniestro.canal, correlation_id,
            )
            return ResultadoReporte(siniestro, repetido=False)
        raise ServicioNoDisponible()  # pragma: no cover - el bucle siempre retorna o lanza

    async def _repetido(self, cmd: ReporteSiniestroCmd, huella: str) -> ResultadoReporte | None:
        existente = await self.repo.obtener_por_clave_idempotencia(cmd.clave_idempotencia)
        if existente is None:
            return None
        if existente.cliente_id != cmd.cliente_id or existente.huella_solicitud != huella:
            raise IdempotenciaConflicto()
        return ResultadoReporte(existente, repetido=True)
