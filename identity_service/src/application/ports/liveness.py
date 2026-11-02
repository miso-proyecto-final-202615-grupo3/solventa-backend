from abc import ABC, abstractmethod
from dataclasses import dataclass


class LivenessAdapterUnavailableError(Exception):
    """El adaptador no pudo procesar la solicitud de prueba de vida."""


class LivenessSessionNotFoundError(Exception):
    """La sesión no existe en el adaptador."""


class LivenessSessionConflictError(Exception):
    """La sesión no permite la transición solicitada."""


class LivenessInvalidCaptureError(Exception):
    """El adaptador rechazó la evidencia por formato, tamaño o marcas de tiempo; no consume intento."""


class LivenessSessionCancelledError(LivenessSessionConflictError):
    """La persona canceló la captura del SDK; no consume intento."""


@dataclass(frozen=True)
class LivenessSessionInfo:
    session_id: str
    expires_at: str
    capture: dict


@dataclass(frozen=True)
class LivenessVerification:
    verification_id: str
    approved: bool
    reason: str | None = None


class LivenessVerificationPort(ABC):
    @abstractmethod
    async def start_session(self, customer_id: str, correlation_id: str) -> LivenessSessionInfo:
        raise NotImplementedError

    @abstractmethod
    async def cancel_session(self, session_id: str, correlation_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def verify(
        self,
        session_id: str,
        customer_id: str,
        nonce: str | None,
        frames: dict[str, bytes],
        captured_at: dict[str, str],
        correlation_id: str,
        sdk_result: str | None = None,
    ) -> LivenessVerification:
        raise NotImplementedError
