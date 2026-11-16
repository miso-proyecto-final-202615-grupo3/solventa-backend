import uuid
from abc import ABC, abstractmethod

from src.domain.productos.entities import ProductoSeguro


class ProductoSeguroRepository(ABC):
    @abstractmethod
    async def guardar(self, producto: ProductoSeguro) -> ProductoSeguro:
        raise NotImplementedError

    @abstractmethod
    async def inicializar_condiciones(
        self, producto_id: uuid.UUID, condiciones: str, version: str
    ) -> None:
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
