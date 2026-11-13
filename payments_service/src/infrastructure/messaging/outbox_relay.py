import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.application.ports.publicador_eventos import PublicacionEventoError, PublicadorEventos
from src.infrastructure.persistence.evento_outbox_repository_impl import (
    SqlAlchemyEventoOutboxRepository,
)

logger = logging.getLogger(__name__)

_OUTBOX_ADVISORY_LOCK_KEY = 0x534F4C564F555442


class OutboxRelay:
    """Publica en el bus los eventos del outbox que quedaron pendientes.

    La entrega es "al menos una vez": si el proceso cae entre publicar y confirmar, el evento
    se publica de nuevo, por eso los consumidores deben ser idempotentes.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker,
        publicador: PublicadorEventos,
        intervalo_segundos: float,
        tamano_lote: int,
    ) -> None:
        self._session_factory = session_factory
        self.publicador = publicador
        self.intervalo_segundos = intervalo_segundos
        self.tamano_lote = tamano_lote

    async def _adquirir_bloqueo(self, session: AsyncSession) -> None:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": _OUTBOX_ADVISORY_LOCK_KEY},
        )

    async def publicar_pendientes(self) -> int:
        """Publica un lote en orden de creación; se detiene en el primer fallo. Devuelve cuántos."""
        publicados = 0
        async with self._session_factory() as session:
            eventos = SqlAlchemyEventoOutboxRepository(session)
            for _ in range(self.tamano_lote):
                await self._adquirir_bloqueo(session)
                pendientes = await eventos.obtener_pendientes(1)
                if not pendientes:
                    break
                evento = pendientes[0]
                try:
                    await self.publicador.publicar(evento.tipo, evento.payload)
                except PublicacionEventoError as exc:
                    logger.warning("No se pudo publicar el evento %s: %s", evento.evento_id, exc)
                    await eventos.registrar_fallo(evento.evento_id, str(exc))
                    await session.commit()
                    break
                await eventos.marcar_publicado(evento.evento_id, datetime.now(UTC))
                await session.commit()
                publicados += 1
        return publicados

    async def ejecutar(self) -> None:
        while True:
            publicados = 0
            try:
                publicados = await self.publicar_pendientes()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Falló el ciclo de publicación del outbox.")
            if publicados < self.tamano_lote:
                await asyncio.sleep(self.intervalo_segundos)
