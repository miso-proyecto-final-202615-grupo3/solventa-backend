"""Dispositivos a los que se envía una notificación (HU4.2.2). Los resuelve MS Identidad a partir del cliente."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class DestinoPush:
    installation_id: str
    token: str
    plataforma: str


class DestinosPush(ABC):
    @abstractmethod
    async def listar(self, cliente_id: UUID, correlation_id: str) -> list[DestinoPush]:
        """Dispositivos `ACTIVO` con token del cliente (CA3: solo los del dueño del siniestro)."""
        raise NotImplementedError

    @abstractmethod
    async def eliminar(self, token: str, correlation_id: str) -> None:
        """Quita un token que el proveedor push ya no acepta (N8)."""
        raise NotImplementedError
