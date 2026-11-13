import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


class CotizacionNoEncontradaError(Exception):
    pass


@dataclass(frozen=True)
class CotizacionPago:
    cotizacion_id: uuid.UUID
    cliente_id: uuid.UUID
    estado: str
    prima_total: Decimal
    moneda: str
    expira_en: datetime


class CotizacionGateway(ABC):
    @abstractmethod
    async def obtener(self, cotizacion_id: uuid.UUID, correlation_id: str) -> CotizacionPago:
        """Lanza CotizacionNoEncontradaError o ServicioNoDisponibleError."""
        raise NotImplementedError

    @abstractmethod
    async def condiciones_aceptadas(self, cotizacion_id: uuid.UUID, correlation_id: str) -> bool:
        """True si la última decisión sobre las condiciones es ACEPTADA."""
        raise NotImplementedError
