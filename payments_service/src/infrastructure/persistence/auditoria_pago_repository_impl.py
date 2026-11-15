import uuid
from datetime import UTC

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.pagos.auditoria import EventoTrazabilidadPago
from src.domain.pagos.repositories import AuditoriaPagoRepository
from src.infrastructure.persistence.models import EventoTrazabilidadPagoModel


def _a_entidad(model: EventoTrazabilidadPagoModel) -> EventoTrazabilidadPago:
    ocurrido_en = model.ocurrido_en
    if ocurrido_en.tzinfo is None:
        ocurrido_en = ocurrido_en.replace(tzinfo=UTC)
    return EventoTrazabilidadPago(
        evento_id=model.evento_id,
        cotizacion_id=model.cotizacion_id,
        cliente_id=model.cliente_id,
        tipo=model.tipo,
        ocurrido_en=ocurrido_en,
        origen=model.origen,
        actor_id=model.actor_id,
        resultado=model.resultado,
        referencia_id=model.referencia_id,
        correlation_id=model.correlation_id,
        detalles=model.detalles,
    )


class SqlAlchemyAuditoriaPagoRepository(AuditoriaPagoRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def agregar(self, evento: EventoTrazabilidadPago) -> None:
        self.session.add(
            EventoTrazabilidadPagoModel(
                evento_id=evento.evento_id,
                cotizacion_id=evento.cotizacion_id,
                cliente_id=evento.cliente_id,
                tipo=evento.tipo,
                ocurrido_en=evento.ocurrido_en,
                origen=evento.origen,
                actor_id=evento.actor_id,
                resultado=evento.resultado,
                referencia_id=evento.referencia_id,
                correlation_id=evento.correlation_id,
                detalles=evento.detalles,
            )
        )
        await self.session.flush()

    async def listar_por_cotizacion(
        self, cotizacion_id: uuid.UUID
    ) -> list[EventoTrazabilidadPago]:
        result = await self.session.execute(
            select(EventoTrazabilidadPagoModel)
            .where(EventoTrazabilidadPagoModel.cotizacion_id == cotizacion_id)
            .order_by(
                EventoTrazabilidadPagoModel.ocurrido_en,
                EventoTrazabilidadPagoModel.evento_id,
            )
        )
        return [_a_entidad(model) for model in result.scalars().all()]
