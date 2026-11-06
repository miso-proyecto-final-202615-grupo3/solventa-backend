import uuid
from abc import ABC, abstractmethod

from src.domain.polizas.entities import Poliza


class PolizaRepository(ABC):
    @abstractmethod
    async def guardar(self, poliza: Poliza) -> Poliza:
        """Persiste la póliza junto con sus coberturas."""
        raise NotImplementedError

    @abstractmethod
    async def obtener_por_id(self, poliza_id: uuid.UUID) -> Poliza | None:
        raise NotImplementedError

    @abstractmethod
    async def obtener_por_numero(self, numero: str) -> Poliza | None:
        raise NotImplementedError

    @abstractmethod
    async def listar_por_cliente(self, cliente_id: uuid.UUID) -> list[Poliza]:
        raise NotImplementedError
