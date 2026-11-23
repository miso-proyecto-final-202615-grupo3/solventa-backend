"""Relay del outbox de MS Siniestros (HU4.2.2, decisión N3; HU4.2.3). Mismo patrón que `payments_service`.

Toma los eventos `PENDIENTE` en orden, uno por vez y con un bloqueo de Postgres para que dos réplicas no
procesen el mismo evento. La entrega es "al menos una vez": si el proceso cae entre enviar y confirmar, el
evento se vuelve a enviar (la app reemplaza la notificación del mismo siniestro y Pagos deduplica por
`clave_idempotencia`).

Tipos que entrega: `SINIESTRO_ESTADO` → push (si las notificaciones están habilitadas) y
`PAGO_INDEMNIZACION_SOLICITADO` → Pagos (HU4.2.3). Un tipo sin destino configurado se queda `PENDIENTE`.
"""
import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.application.ports.solicitudes_pago import SolicitudesPago
from src.application.use_cases.notificar_cambio_estado_use_case import NotificarCambioEstadoUseCase
from src.infrastructure.persistence.siniestros_repository_impl import (
    SqlAlchemyEventoOutboxRepository,
    SqlAlchemySiniestroRepository,
)

logger = logging.getLogger(__name__)

_OUTBOX_ADVISORY_LOCK_KEY = 0x534F4C564F555442
TIPO_ESTADO = "SINIESTRO_ESTADO"
TIPO_PAGO = "PAGO_INDEMNIZACION_SOLICITADO"


class OutboxRelay:
    def __init__(
        self,
        session_factory: async_sessionmaker,
        notificar: NotificarCambioEstadoUseCase | None,
        intervalo_segundos: float,
        max_intentos: int,
        tamano_lote: int = 20,
        pagos: SolicitudesPago | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._notificar = notificar
        self._pagos = pagos
        self._intervalo = intervalo_segundos
        self._max_intentos = max_intentos
        self._tamano_lote = tamano_lote
        self._tipos = [t for t, destino in ((TIPO_ESTADO, notificar), (TIPO_PAGO, pagos)) if destino is not None]

    @staticmethod
    async def _bloquear(session: AsyncSession) -> None:
        # En SQLite (pruebas) no hay bloqueos de aplicación; hay un solo proceso.
        if session.bind.dialect.name == "postgresql":
            await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _OUTBOX_ADVISORY_LOCK_KEY})

    async def publicar_pendientes(self) -> int:
        """Procesa hasta `tamano_lote` eventos; se detiene en el primer fallo. Devuelve cuántos publicó."""
        publicados = 0
        async with self._session_factory() as session:
            outbox = SqlAlchemyEventoOutboxRepository(session)
            siniestros = SqlAlchemySiniestroRepository(session)
            for _ in range(self._tamano_lote):
                await self._bloquear(session)
                pendientes = await outbox.obtener_pendientes(1, self._tipos)
                if not pendientes:
                    await session.commit()
                    break
                evento = pendientes[0]
                try:
                    if evento.tipo == TIPO_PAGO:
                        await self._pagos.solicitar(evento.payload, str(evento.evento_id))
                    else:
                        siniestro = await siniestros.obtener_por_id(evento.agregado_id)
                        if siniestro is None:
                            raise LookupError("siniestro no encontrado")
                        await self._notificar.ejecutar(evento, siniestro)
                except Exception as exc:  # cualquier fallo deja el evento para reintentar (o FALLIDO)
                    logger.warning(
                        "outbox_evento_fallido evento_id=%s tipo=%s error=%s", evento.evento_id, evento.tipo, type(exc).__name__
                    )
                    await outbox.registrar_fallo(evento.evento_id, f"{type(exc).__name__}: {exc}", self._max_intentos)
                    await session.commit()
                    break
                await outbox.marcar_publicado(evento.evento_id, datetime.now(UTC))
                await session.commit()
                publicados += 1
        return publicados

    async def ejecutar(self) -> None:
        logger.info("outbox_relay_iniciado intervalo_s=%s tipos=%s", self._intervalo, ",".join(self._tipos))
        while True:
            try:
                await self.publicar_pendientes()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("outbox_relay_error")
            await asyncio.sleep(self._intervalo)
