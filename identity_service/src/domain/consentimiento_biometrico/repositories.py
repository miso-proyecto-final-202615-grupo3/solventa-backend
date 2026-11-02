import uuid
from abc import ABC, abstractmethod

from src.domain.consentimiento_biometrico.entities import DecisionConsentimientoBiometrico


class ConsentimientoBiometricoRepository(ABC):
    """Registro de solo inserción: cada decisión queda como evidencia auditable."""

    @abstractmethod
    async def registrar(self, decision: DecisionConsentimientoBiometrico) -> None:
        raise NotImplementedError

    @abstractmethod
    async def ultima_decision(self, cliente_id: uuid.UUID) -> DecisionConsentimientoBiometrico | None:
        raise NotImplementedError
