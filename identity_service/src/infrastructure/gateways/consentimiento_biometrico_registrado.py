from uuid import UUID

from src.application.ports.consentimiento_biometrico import ConsentimientoBiometricoPort
from src.domain.consentimiento_biometrico.entities import EstadoConsentimientoBiometrico
from src.domain.consentimiento_biometrico.repositories import ConsentimientoBiometricoRepository


class ConsentimientoBiometricoRegistrado(ConsentimientoBiometricoPort):
    """La activación solo continúa si la última decisión del cliente acepta la versión vigente.

    `REQUIRE_BIOMETRIC_CONSENT=false` deja pasar sin consultar (solo para entornos de demostración).
    """

    def __init__(
        self,
        consentimientos: ConsentimientoBiometricoRepository,
        version_vigente: str,
        require_consent: bool = True,
    ) -> None:
        self._consentimientos = consentimientos
        self._version_vigente = version_vigente
        self._require_consent = require_consent

    async def otorgado(self, cliente_id: UUID) -> bool:
        if not self._require_consent:
            return True
        ultima = await self._consentimientos.ultima_decision(cliente_id)
        return EstadoConsentimientoBiometrico.desde(ultima, self._version_vigente).otorgado
