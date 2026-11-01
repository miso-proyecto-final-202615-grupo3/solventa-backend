import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class DecisionBiometrica(StrEnum):
    ACEPTADO = "ACEPTADO"
    RECHAZADO = "RECHAZADO"


@dataclass(frozen=True)
class DecisionConsentimientoBiometrico:
    """Una decisión del cliente. Se guarda siempre (también el rechazo) y nunca se modifica."""

    cliente_id: uuid.UUID
    decision: DecisionBiometrica
    version_terminos: str
    installation_id: uuid.UUID
    decidido_en: datetime
    registrado_en: datetime
    canal: str = "APP_MOVIL"


@dataclass(frozen=True)
class EstadoConsentimientoBiometrico:
    otorgado: bool
    version_vigente: str
    version_aceptada: str | None
    decidido_en: datetime | None

    @classmethod
    def desde(cls, ultima: DecisionConsentimientoBiometrico | None, version_vigente: str) -> "EstadoConsentimientoBiometrico":
        """Vale la última decisión; solo otorga si es una aceptación de la versión vigente del texto."""
        if ultima is None:
            return cls(False, version_vigente, None, None)
        aceptada = ultima.version_terminos if ultima.decision == DecisionBiometrica.ACEPTADO else None
        return cls(aceptada == version_vigente, version_vigente, aceptada, ultima.decidido_en)
