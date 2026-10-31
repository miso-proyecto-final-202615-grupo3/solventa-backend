import os
import secrets
import uuid

from src.application.ports import ProviderSessionStarted, ProviderUnavailableError, ProviderVerificationResult
from src.core.config import settings


class DiditProvider:
    """Doble de Didit para demo: mantiene el contrato sin requerir cuenta externa."""

    name = "didit"

    def start_session(self) -> ProviderSessionStarted:
        if not settings.DIDIT_ENABLED:
            raise ProviderUnavailableError()
        return ProviderSessionStarted(capture={"tipo": "FRAMES", "reto": {"gesto": "BLINK", "nonce": secrets.token_urlsafe(24)}})

    def verify(self, session: dict, frames: dict[str, bytes]) -> ProviderVerificationResult:
        status = os.getenv("MOCK_DIDIT_STATUS", "APPROVED").upper()
        return ProviderVerificationResult(
            f"didit-mock-{uuid.uuid4()}", status == "APPROVED",
            None if status == "APPROVED" else "PRUEBA_VIDA_FALLIDA",
        )
