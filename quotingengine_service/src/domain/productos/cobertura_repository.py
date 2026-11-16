import uuid
from abc import ABC, abstractmethod

from src.domain.productos.entities import Cobertura


class CoberturaRepository(ABC):
    @abstractmethod
    async def guardar(self, cobertura: Cobertura) -> Cobertura:
        raise NotImplementedError

    @abstractmethod
    async def listar_activas_por_producto(self, producto_id: uuid.UUID) -> list[Cobertura]:
        raise NotImplementedError

    @abstractmethod
    async def listar_activas_por_productos(
        self, producto_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[Cobertura]]:
        raise NotImplementedError
