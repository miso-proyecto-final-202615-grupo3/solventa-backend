import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.eventos.entities import EstadoEvento, EventoOutbox
from src.domain.eventos.repositories import EventoOutboxRepository
from src.infrastructure.persistence.models import EventoOutboxModel


def _a_entidad(model: EventoOutboxModel) -> EventoOutbox:
    return EventoOutbox(
        evento_id=model.evento_id,
        tipo=model.tipo,
        agregado_id=model.agregado_id,
        payload=model.payload,
        estado=EstadoEvento(model.estado),
        intentos=model.intentos,
        ultimo_error=model.ultimo_error,
        creado_en=model.creado_en,
        publicado_en=model.publicado_en,
    )


class SqlAlchemyEventoOutboxRepository(EventoOutboxRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def agregar(self, evento: EventoOutbox) -> None:
        self.session.add(
            EventoOutboxModel(
                evento_id=evento.evento_id,
                tipo=evento.tipo,
                agregado_id=evento.agregado_id,
                payload=evento.payload,
                estado=evento.estado.value,
                intentos=evento.intentos,
                ultimo_error=evento.ultimo_error,
                creado_en=evento.creado_en,
                publicado_en=evento.publicado_en,
            )
        )
        await self.session.flush()

    async def obtener_pendientes(self, limite: int) -> list[EventoOutbox]:
        result = await self.session.execute(
            select(EventoOutboxModel)
            .where(EventoOutboxModel.estado == EstadoEvento.PENDIENTE.value)
            .order_by(EventoOutboxModel.creado_en, EventoOutboxModel.evento_id)
            .limit(limite)
            # Varias réplicas pueden sondear a la vez: cada una toma eventos distintos.
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
        return [_a_entidad(model) for model in result.scalars()]

    async def marcar_publicado(self, evento_id: uuid.UUID, cuando: datetime) -> None:
        await self.session.execute(
            update(EventoOutboxModel)
            .where(EventoOutboxModel.evento_id == evento_id)
            .values(
                estado=EstadoEvento.PUBLICADO.value,
                publicado_en=cuando,
                intentos=EventoOutboxModel.intentos + 1,
                ultimo_error=None,
            )
            .execution_options(synchronize_session=False)
        )

    async def registrar_fallo(self, evento_id: uuid.UUID, detalle: str) -> None:
        await self.session.execute(
            update(EventoOutboxModel)
            .where(EventoOutboxModel.evento_id == evento_id)
            .values(intentos=EventoOutboxModel.intentos + 1, ultimo_error=detalle[:500])
            .execution_options(synchronize_session=False)
        )
