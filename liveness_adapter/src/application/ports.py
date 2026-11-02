from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProviderSessionStarted:
    """Captura normalizada (`tipo` FRAMES o SDK) y referencia opcional de la sesión en el proveedor."""

    capture: dict
    provider_session_id: str | None = None


@dataclass(frozen=True)
class ProviderVerificationResult:
    verification_id: str
    approved: bool
    reason: str | None = None


class LivenessProvider(Protocol):
    """Estrategia intercambiable para cada proveedor de prueba de vida."""

    name: str
    capture_type: str
    requires_budget: bool

    def start_session(self, customer_id: str, session_id: str) -> ProviderSessionStarted: ...

    def verify(
        self, session: dict, frames: dict[str, bytes], sdk_result: str | None
    ) -> ProviderVerificationResult: ...


class ProviderNotRegisteredError(Exception):
    pass


class ProviderUnavailableError(Exception):
    pass
