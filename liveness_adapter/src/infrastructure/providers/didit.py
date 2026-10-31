import uuid

from src.application.ports import ProviderSessionStarted, ProviderUnavailableError, ProviderVerificationResult
from src.core.config import settings


class DiditProvider:
    """Proveedor SDK desactivado por defecto; credenciales siempre llegan por secretos."""

    name = "didit"

    def start_session(self) -> ProviderSessionStarted:
        if not settings.DIDIT_ENABLED or not settings.DIDIT_API_KEY or not settings.DIDIT_WORKFLOW_ID:
            raise ProviderUnavailableError()
        token = f"didit-{uuid.uuid4()}"
        return ProviderSessionStarted(capture={"tipo": "SDK", "sdk": {"nombre": "DIDIT", "session_token": token}})

    def verify(self, session: dict, frames: dict[str, bytes]) -> ProviderVerificationResult:
        raise ProviderUnavailableError()
