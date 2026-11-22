"""Consumidor de eventos paramétricos (HU4.2.3, ASR-ESC-002, supuesto P2).

El "bus durable" es la tabla `evento_externo`: cada réplica toma un evento `RECIBIDO` con
`FOR UPDATE SKIP LOCKED` (competing consumers). Un error transitorio deja el evento `RECIBIDO` para
reintentarlo en la siguiente vuelta (backoff = intervalo) hasta `max_intentos`; luego queda `FALLIDO`
(la DLQ del diseño). Un evento que no se puede interpretar queda `DESCARTADO` sin reintentos.
"""
import asyncio
import logging
import uuid
from collections.abc import Callable
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.application.ports.polizas import PolizasPort
from src.application.use_cases.eventos_parametricos_use_cases import (
    ProcesarEventoParametricoUseCase,
    RepositoriosParametricos,
)
from src.domain.siniestros.parametricos import EstadoEvento, EventoNoProcesable
from src.infrastructure.persistence.models import EventoExternoModel
from src.infrastructure.persistence.polizas_parametricas_repository_impl import SqlAlchemyPolizaParametricaRepository
from src.infrastructure.persistence.siniestros_repository_impl import (
    SqlAlchemyActivacionParametricaRepository,
    SqlAlchemyActivacionPolizaRepository,
    SqlAlchemyEventoExternoRepository,
    SqlAlchemyEventoOutboxRepository,
    SqlAlchemyIndemnizacionRepository,
    SqlAlchemySiniestroRepository,
)

logger = logging.getLogger(__name__)


def repositorios(session: AsyncSession) -> RepositoriosParametricos:
    return RepositoriosParametricos(
        eventos=SqlAlchemyEventoExternoRepository(session),
        suscripciones=SqlAlchemyPolizaParametricaRepository(session),
        activaciones=SqlAlchemyActivacionParametricaRepository(session),
        activaciones_poliza=SqlAlchemyActivacionPolizaRepository(session),
        siniestros=SqlAlchemySiniestroRepository(session),
        indemnizaciones=SqlAlchemyIndemnizacionRepository(session),
        outbox=SqlAlchemyEventoOutboxRepository(session),
    )


class ProcesadorEventosParametricos:
    def __init__(
        self,
        session_factory: async_sessionmaker,
        polizas: PolizasPort,
        reloj: Callable[[], datetime],
        estados_elegibles: list[str],
        intervalo_segundos: float,
        max_intentos: int,
        tamano_lote: int = 20,
    ) -> None:
        self._session_factory = session_factory
        self._polizas = polizas
        self._reloj = reloj
        self._estados = estados_elegibles
        self._intervalo = intervalo_segundos
        self._max_intentos = max_intentos
        self._tamano_lote = tamano_lote

    async def procesar_pendientes(self) -> int:
        """Procesa hasta `tamano_lote` eventos; se detiene en el primer error transitorio."""
        procesados = 0
        for _ in range(self._tamano_lote):
            async with self._session_factory() as session:
                repos = repositorios(session)
                evento = await repos.eventos.tomar_siguiente_recibido()
                if evento is None:
                    await session.commit()
                    break
                caso = ProcesarEventoParametricoUseCase(session, repos, self._polizas, self._reloj, self._estados)
                try:
                    await caso.ejecutar(evento)
                except EventoNoProcesable as exc:
                    await session.rollback()
                    await self._registrar(evento.evento_externo_id, exc.mensaje, descartar=True)
                except Exception as exc:  # transitorio: MS Pólizas caído, base de datos, etc.
                    await session.rollback()
                    await self._registrar(evento.evento_externo_id, f"{type(exc).__name__}: {exc}", descartar=False)
                    break
            procesados += 1
        return procesados

    async def _registrar(self, evento_externo_id: uuid.UUID, error: str, descartar: bool) -> None:
        async with self._session_factory() as session:
            modelo = await session.get(EventoExternoModel, evento_externo_id, with_for_update=True)
            if modelo is None:
                return
            modelo.intentos += 1
            modelo.ultimo_error = error[:500]
            if descartar:
                modelo.estado = EstadoEvento.DESCARTADO.value
            elif modelo.intentos >= self._max_intentos:
                modelo.estado = EstadoEvento.FALLIDO.value
            if modelo.estado != EstadoEvento.RECIBIDO.value:
                modelo.procesado_en = self._reloj()
            await session.commit()
            logger.warning(
                "evento_parametrico_error event_id=%s estado=%s intentos=%s error=%s",
                modelo.event_id, modelo.estado, modelo.intentos, error.split(":")[0],
            )

    async def ejecutar(self) -> None:
        logger.info("procesador_parametrico_iniciado intervalo_s=%s", self._intervalo)
        while True:
            try:
                await self.procesar_pendientes()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("procesador_parametrico_error")
            await asyncio.sleep(self._intervalo)
