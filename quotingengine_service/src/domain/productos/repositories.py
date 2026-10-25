import uuid
from abc import ABC, abstractmethod

from src.domain.productos.entities import Cobertura, ProductoSeguro


class ProductoSeguroRepository(ABC):
    @abstractmethod
    async def guardar(self, producto: ProductoSeguro) -> ProductoSeguro:
        raise NotImplementedError

    @abstractmethod
    async def obtener_por_id(self, producto_id: uuid.UUID) -> ProductoSeguro | None:
        raise NotImplementedError

    @abstractmethod
    async def obtener_por_codigo(self, codigo: str) -> ProductoSeguro | None:
        raise NotImplementedError

    @abstractmethod
    async def listar_activos(self) -> list[ProductoSeguro]:
        raise NotImplementedError


class CoberturaRepository(ABC):
    @abstractmethod
    async def guardar(self, cobertura: Cobertura) -> Cobertura:
        raise NotImplementedError

    @abstractmethod
    async def listar_activas_por_producto(
        self, producto_id: uuid.UUID
    ) -> list[Cobertura]:
        raise NotImplementedError

    @abstractmethod
    async def listar_activas_por_productos(
        self, producto_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[Cobertura]]:
        raise NotImplementedError
