import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any


class CotizacionNoEncontradaError(Exception):
    pass


@dataclass(frozen=True)
class CoberturaCotizada:
    cobertura_id: uuid.UUID
    codigo: str
    nombre: str
    prima: Decimal
    limite_asegurado: Decimal
    deducible: Decimal


@dataclass(frozen=True)
class ImpuestoCotizado:
    concepto: str
    tasa: Decimal
    valor: Decimal


@dataclass(frozen=True)
class CotizacionEmision:
    cotizacion_id: uuid.UUID
    cliente_id: uuid.UUID
    producto_codigo: str
    moneda: str
    prima_base: Decimal
    prima_neta: Decimal
    prima_total: Decimal
    impuestos: tuple[ImpuestoCotizado, ...]
    coberturas: tuple[CoberturaCotizada, ...]


@dataclass(frozen=True)
class ProductoEmision:
    producto_id: uuid.UUID
    codigo: str
    nombre: str
    ramo: str


@dataclass(frozen=True)
class CondicionesEmision:
    version_condiciones_generales: str
    condiciones_particulares: dict[str, Any] = field(default_factory=dict)
    aceptadas_en: datetime | None = None


class CotizacionGateway(ABC):
    @abstractmethod
    async def obtener_cotizacion(
        self, cotizacion_id: uuid.UUID, correlation_id: str
    ) -> CotizacionEmision:
        """Lanza CotizacionNoEncontradaError o ServicioNoDisponibleError."""
        raise NotImplementedError

    @abstractmethod
    async def obtener_producto(self, codigo: str, correlation_id: str) -> ProductoEmision:
        raise NotImplementedError

    @abstractmethod
    async def obtener_condiciones(
        self, cotizacion_id: uuid.UUID, correlation_id: str
    ) -> CondicionesEmision:
        raise NotImplementedError
