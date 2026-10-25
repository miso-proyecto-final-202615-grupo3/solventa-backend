from uuid import UUID

from src.application.ports.consentimiento_biometrico import ConsentimientoBiometricoPort


class ConsentimientoBiometricoPermisivo(ConsentimientoBiometricoPort):
    """Puente temporal hasta que HU3.1.3 entregue el consentimiento real."""

    def __init__(self, require_consent: bool = False) -> None:
        self._require_consent = require_consent

    async def otorgado(self, cliente_id: UUID) -> bool:
        # Si el requisito está activo no se autoriza por defecto: falla cerrada.
        return not self._require_consent
