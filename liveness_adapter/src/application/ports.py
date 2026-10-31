from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProviderSessionStarted:
    capture: dict


@dataclass(frozen=True)
class ProviderVerificationResult:
    verification_id: str
    approved: bool
    reason: str | None = None


class LivenessProvider(Protocol):
    """Estrategia intercambiable para cada proveedor de prueba de vida."""

    name: str

    def start_session(self) -> ProviderSessionStarted: ...

    def verify(self, session: dict, frames: dict[str, bytes]) -> ProviderVerificationResult: ...


class ProviderNotRegisteredError(Exception):
    pass


class ProviderUnavailableError(Exception):
    pass
