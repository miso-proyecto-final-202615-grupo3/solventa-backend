import uuid
from abc import ABC, abstractmethod

from src.domain.cotizaciones.entities import Cotizacion, CotizacionCobertura


class CotizacionRepository(ABC):
    @abstractmethod
    async def guardar(self, cotizacion: Cotizacion) -> Cotizacion:
        raise NotImplementedError

    @abstractmethod
    async def obtener_por_id(self, cotizacion_id: uuid.UUID) -> Cotizacion | None:
        raise NotImplementedError

    @abstractmethod
    async def listar_por_cliente(self, cliente_id: uuid.UUID) -> list[Cotizacion]:
        raise NotImplementedError


class CotizacionCoberturaRepository(ABC):
    @abstractmethod
    async def guardar_todas(
        self, detalles: list[CotizacionCobertura]
    ) -> list[CotizacionCobertura]:
        raise NotImplementedError

    @abstractmethod
    async def listar_por_cotizacion(
        self, cotizacion_id: uuid.UUID
    ) -> list[CotizacionCobertura]:
        raise NotImplementedError
