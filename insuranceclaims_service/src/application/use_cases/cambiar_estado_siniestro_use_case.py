from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.siniestros.entities import EventoOutbox, Siniestro
from src.domain.siniestros.enums import EstadoSiniestro
from src.domain.siniestros.errores import SiniestroNoEncontrado
from src.domain.siniestros.repositories import EventoOutboxRepository, IndemnizacionRepository, SiniestroRepository


class CambiarEstadoSiniestroUseCase:
    def __init__(
        self,
        db: AsyncSession,
        siniestros: SiniestroRepository,
        outbox: EventoOutboxRepository,
        reloj: Callable[[], datetime],
        indemnizaciones: IndemnizacionRepository | None = None,
    ) -> None:
        self._db, self._siniestros, self._outbox, self._reloj = db, siniestros, outbox, reloj
        self._indemnizaciones = indemnizaciones

    async def ejecutar(self, siniestro_id: UUID, estado: str) -> tuple[Siniestro, bool]:
        siniestro = await self._siniestros.obtener_por_id_para_actualizar(siniestro_id)
        if siniestro is None:
            raise SiniestroNoEncontrado()
        cambio = siniestro.cambiar_estado(estado, self._reloj())
        if cambio:
            await self._siniestros.actualizar(siniestro)
            if estado == EstadoSiniestro.PAGADO.value and self._indemnizaciones is not None:
                # HU4.2.3 (P6): el pago del siniestro cierra la indemnización.
                indemnizacion = await self._indemnizaciones.obtener_de_siniestro(siniestro.siniestro_id)
                if indemnizacion is not None:
                    indemnizacion.estado = "PAGADA"
                    await self._indemnizaciones.actualizar(indemnizacion)
            evento = EventoOutbox(tipo="SINIESTRO_ESTADO", agregado_id=siniestro.siniestro_id, payload={
                "tipo": "SINIESTRO_ESTADO", "siniestro_id": str(siniestro.siniestro_id), "numero": siniestro.numero or "",
                "estado": siniestro.estado, "canal": siniestro.canal,
            })
            await self._outbox.guardar(evento)
        await self._db.commit()
        return siniestro, cambio
