from abc import ABC, abstractmethod
from dataclasses import dataclass


class LivenessAdapterUnavailableError(Exception):
    """El adaptador no pudo procesar la solicitud de prueba de vida."""


@dataclass(frozen=True)
class LivenessSessionInfo:
    session_id: str
    expires_at: str
    capture: dict


class LivenessVerificationPort(ABC):
    @abstractmethod
    async def start_session(self, customer_id: str, correlation_id: str) -> LivenessSessionInfo:
        raise NotImplementedError
