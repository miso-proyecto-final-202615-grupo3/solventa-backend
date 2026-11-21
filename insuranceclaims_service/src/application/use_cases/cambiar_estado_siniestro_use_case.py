from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.siniestros.entities import Siniestro
from src.domain.siniestros.entities import EventoOutbox
from src.domain.siniestros.errores import SiniestroNoEncontrado
from src.domain.siniestros.repositories import EventoOutboxRepository, SiniestroRepository


class CambiarEstadoSiniestroUseCase:
    def __init__(self, db: AsyncSession, siniestros: SiniestroRepository, outbox: EventoOutboxRepository, reloj: Callable[[], datetime]) -> None:
        self._db, self._siniestros, self._outbox, self._reloj = db, siniestros, outbox, reloj

    async def ejecutar(self, siniestro_id: UUID, estado: str) -> tuple[Siniestro, bool]:
        siniestro = await self._siniestros.obtener_por_id_para_actualizar(siniestro_id)
        if siniestro is None:
            raise SiniestroNoEncontrado()
        cambio = siniestro.cambiar_estado(estado, self._reloj())
        if cambio:
            await self._siniestros.actualizar(siniestro)
            evento = EventoOutbox(tipo="SINIESTRO_ESTADO", agregado_id=siniestro.siniestro_id, payload={
                "tipo": "SINIESTRO_ESTADO", "siniestro_id": str(siniestro.siniestro_id), "numero": siniestro.numero or "", "estado": siniestro.estado,
            })
            await self._outbox.guardar(evento)
        await self._db.commit()
        return siniestro, cambio
