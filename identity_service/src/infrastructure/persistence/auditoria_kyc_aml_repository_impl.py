import uuid
from datetime import UTC

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.verificaciones_kyc_aml.auditoria import EventoTrazabilidadKycAml
from src.domain.verificaciones_kyc_aml.repositories import AuditoriaKycAmlRepository
from src.infrastructure.persistence.models import EventoTrazabilidadKycAmlModel


def _a_entidad(model: EventoTrazabilidadKycAmlModel) -> EventoTrazabilidadKycAml:
    ocurrido_en = model.ocurrido_en
    if ocurrido_en.tzinfo is None:
        ocurrido_en = ocurrido_en.replace(tzinfo=UTC)
    return EventoTrazabilidadKycAml(
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


class SqlAlchemyAuditoriaKycAmlRepository(AuditoriaKycAmlRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def agregar(self, evento: EventoTrazabilidadKycAml) -> None:
        self.session.add(
            EventoTrazabilidadKycAmlModel(
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
    ) -> list[EventoTrazabilidadKycAml]:
        result = await self.session.execute(
            select(EventoTrazabilidadKycAmlModel)
            .where(EventoTrazabilidadKycAmlModel.cotizacion_id == cotizacion_id)
            .order_by(
                EventoTrazabilidadKycAmlModel.ocurrido_en,
                case(
                    (EventoTrazabilidadKycAmlModel.tipo == "KYC_AML_SOLICITADA", 0),
                    (EventoTrazabilidadKycAmlModel.tipo == "KYC_AML_INICIADA", 1),
                    else_=2,
                ),
                EventoTrazabilidadKycAmlModel.evento_id,
            )
        )
        return [_a_entidad(model) for model in result.scalars().all()]

    async def cotizacion_de_verificacion(
        self, cliente_id: uuid.UUID, verificacion_id: uuid.UUID
    ) -> uuid.UUID | None:
        result = await self.session.execute(
            select(EventoTrazabilidadKycAmlModel.cotizacion_id)
            .where(
                EventoTrazabilidadKycAmlModel.cliente_id == cliente_id,
                EventoTrazabilidadKycAmlModel.referencia_id == str(verificacion_id),
            )
            .order_by(EventoTrazabilidadKycAmlModel.ocurrido_en)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def ultimo_evento_verificacion(
        self, cliente_id: uuid.UUID, verificacion_id: uuid.UUID, tipo: str
    ) -> EventoTrazabilidadKycAml | None:
        result = await self.session.execute(
            select(EventoTrazabilidadKycAmlModel)
            .where(
                EventoTrazabilidadKycAmlModel.cliente_id == cliente_id,
                EventoTrazabilidadKycAmlModel.referencia_id == str(verificacion_id),
                EventoTrazabilidadKycAmlModel.tipo == tipo,
            )
            .order_by(
                EventoTrazabilidadKycAmlModel.ocurrido_en.desc(),
                EventoTrazabilidadKycAmlModel.evento_id.desc(),
            )
            .limit(1)
        )
        model = result.scalar_one_or_none()
        return _a_entidad(model) if model else None
