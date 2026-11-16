import uuid
from abc import ABC, abstractmethod

from src.domain.cotizaciones.entities import CotizacionCobertura


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
