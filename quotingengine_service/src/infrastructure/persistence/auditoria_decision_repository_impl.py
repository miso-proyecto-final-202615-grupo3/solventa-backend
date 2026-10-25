import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.auditoria.entities import AuditoriaDecision
from src.domain.auditoria.repositories import AuditoriaDecisionRepository
from src.infrastructure.persistence.models import AuditoriaDecisionModel


def _a_entidad(model: AuditoriaDecisionModel) -> AuditoriaDecision:
    return AuditoriaDecision(
        auditoria_decision_id=model.auditoria_decision_id,
        cotizacion_id=model.cotizacion_id,
        regla_rating_id=model.regla_rating_id,
        tipo_decision=model.tipo_decision,
        entradas=model.entradas,
        resultado=model.resultado,
        decidida_en=model.decidida_en,
    )


class SqlAlchemyAuditoriaDecisionRepository(AuditoriaDecisionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def guardar(self, auditoria: AuditoriaDecision) -> AuditoriaDecision:
        self.session.add(
            AuditoriaDecisionModel(
                auditoria_decision_id=auditoria.auditoria_decision_id,
                cotizacion_id=auditoria.cotizacion_id,
                regla_rating_id=auditoria.regla_rating_id,
                tipo_decision=auditoria.tipo_decision,
                entradas=auditoria.entradas,
                resultado=auditoria.resultado,
            )
        )
        await self.session.flush()
        return auditoria

    async def listar_por_cotizacion(
        self, cotizacion_id: uuid.UUID
    ) -> list[AuditoriaDecision]:
        result = await self.session.execute(
            select(AuditoriaDecisionModel).where(
                AuditoriaDecisionModel.cotizacion_id == cotizacion_id
            )
        )
        return [_a_entidad(m) for m in result.scalars().all()]
