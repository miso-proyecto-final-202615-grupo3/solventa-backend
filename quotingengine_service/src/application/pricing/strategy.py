import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any

from src.application.ports.perfil_cliente_gateway import PerfilCliente
from src.domain.productos.entities import ProductoSeguro
from src.domain.open_data import PerfilTerritorial
from src.domain.reglas_rating.entities import ReglaRating


class TipoAjuste(StrEnum):
    DEDUCCION = "DEDUCCION"
    RECARGO = "RECARGO"


@dataclass(frozen=True)
class AjustePrima:
    concepto: str
    tipo: TipoAjuste
    valor: Decimal
    motivo: str


@dataclass(frozen=True)
class ImpuestoPrima:
    concepto: str
    tasa: Decimal
    valor: Decimal


@dataclass(frozen=True)
class SenalesPricing:
    """Datos externos recolectados para el cálculo (perfil, Open Finance/Open Data)."""

    perfil: PerfilCliente | None = None
    perfil_territorial: PerfilTerritorial | None = None
    degradaciones: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContextoPricing:
    cliente_id: uuid.UUID
    producto: ProductoSeguro
    regla: ReglaRating
    parametros: dict[str, Any]
    senales: SenalesPricing = field(default_factory=SenalesPricing)


@dataclass(frozen=True)
class ResultadoPricing:
    prima_base: Decimal
    ajustes: list[AjustePrima]
    impuestos: list[ImpuestoPrima]
    prima_neta: Decimal
    prima_total: Decimal
    moneda: str
    degradaciones: tuple[str, ...] = ()

    @property
    def degradado(self) -> bool:
        return bool(self.degradaciones)


class PricingStrategy(ABC):
    """Algoritmo de cálculo de prima de un tipo de producto."""

    @property
    @abstractmethod
    def codigo_producto(self) -> str:
        raise NotImplementedError

    async def recolectar_senales(
        self,
        cliente_id: uuid.UUID,
        parametros: dict[str, Any] | None = None,
    ) -> SenalesPricing:
        """Obtiene los datos externos que el algoritmo necesita (puede ser I/O)."""
        return SenalesPricing()

    @abstractmethod
    def calcular(self, contexto: ContextoPricing) -> ResultadoPricing:
        raise NotImplementedError
