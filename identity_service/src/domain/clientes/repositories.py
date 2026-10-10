from abc import ABC, abstractmethod

from src.domain.clientes.entities import Cliente


class ClienteRepository(ABC):
    @abstractmethod
    async def existe_por_correo(self, correo: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def existe_por_documento(
        self, tipo_documento: str, numero_identificacion: str
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def guardar(self, cliente: Cliente) -> None:
        raise NotImplementedError