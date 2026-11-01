import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.consentimiento_biometrico.entities import (
    DecisionBiometrica,
    DecisionConsentimientoBiometrico,
)
from src.domain.consentimiento_biometrico.repositories import ConsentimientoBiometricoRepository
from src.infrastructure.persistence.models import ConsentimientoBiometricoModel


class SqlAlchemyConsentimientoBiometricoRepository(ConsentimientoBiometricoRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def registrar(self, decision: DecisionConsentimientoBiometrico) -> None:
        self.session.add(
            ConsentimientoBiometricoModel(
                cliente_id=decision.cliente_id,
                decision=decision.decision.value,
                version_terminos=decision.version_terminos,
                installation_id=decision.installation_id,
                canal=decision.canal,
                decidido_en=decision.decidido_en,
                registrado_en=decision.registrado_en,
            )
        )
        await self.session.flush()

    async def ultima_decision(self, cliente_id: uuid.UUID) -> DecisionConsentimientoBiometrico | None:
        model = (
            await self.session.execute(
                select(ConsentimientoBiometricoModel)
                .where(ConsentimientoBiometricoModel.cliente_id == cliente_id)
                .order_by(ConsentimientoBiometricoModel.registrado_en.desc(), ConsentimientoBiometricoModel.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if model is None:
            return None
        return DecisionConsentimientoBiometrico(
            cliente_id=model.cliente_id,
            decision=DecisionBiometrica(model.decision),
            version_terminos=model.version_terminos,
            installation_id=model.installation_id,
            decidido_en=model.decidido_en,
            registrado_en=model.registrado_en,
            canal=model.canal,
        )
