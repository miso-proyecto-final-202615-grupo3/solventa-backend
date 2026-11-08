import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.condiciones.decision_condiciones_repository import DecisionCondicionesRepository
from src.domain.condiciones.entities import Decision, DecisionCondiciones
from src.infrastructure.persistence.models import DecisionCondicionesModel


class SqlAlchemyDecisionCondicionesRepository(DecisionCondicionesRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def guardar(self, decision: DecisionCondiciones) -> None:
        self.session.add(DecisionCondicionesModel(
            decision_condiciones_id=decision.decision_condiciones_id,
            condiciones_cotizacion_id=decision.condiciones_cotizacion_id,
            cliente_id=decision.cliente_id,
            decision=decision.decision.value,
            decidida_en=decision.decidida_en,
        ))
        await self.session.flush()

    async def obtener_ultima(self, condiciones_id: uuid.UUID) -> DecisionCondiciones | None:
        result = await self.session.execute(
            select(DecisionCondicionesModel)
            .where(DecisionCondicionesModel.condiciones_cotizacion_id == condiciones_id)
            .order_by(DecisionCondicionesModel.decidida_en.desc(), DecisionCondicionesModel.decision_condiciones_id.desc())
            .limit(1)
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return DecisionCondiciones(
            decision_condiciones_id=model.decision_condiciones_id,
            condiciones_cotizacion_id=model.condiciones_cotizacion_id,
            cliente_id=model.cliente_id,
            decision=Decision(model.decision),
            decidida_en=model.decidida_en,
        )
