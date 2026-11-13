from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal


class ProveedorPagoError(Exception):
    """El proveedor no está disponible o respondió de forma inesperada: el resultado es incierto."""

    def __init__(self, codigo: str, detalle: str = "") -> None:
        self.codigo = codigo
        self.detalle = detalle
        super().__init__(f"{codigo}: {detalle}" if detalle else codigo)


class SolicitudInvalidaError(ProveedorPagoError):
    """El proveedor rechazó la solicitud por sus datos (p. ej. token inválido): no hubo cobro."""


@dataclass(frozen=True)
class DatosTarjeta:
    numero_tarjeta: str = field(repr=False)
    mes_expiracion: int = field(repr=False)
    anio_expiracion: int = field(repr=False)
    cvv: str = field(repr=False)


@dataclass(frozen=True)
class SolicitudCobro:
    referencia: str
    monto: Decimal
    moneda: str
    # Correo del pagador en PayPal o token de la tarjeta; nunca el número de la tarjeta.
    credencial: str = field(repr=False)
    correlation_id: str


@dataclass(frozen=True)
class ResultadoCobro:
    aprobado: bool
    referencia: str
    codigo_rechazo: str | None = None
    tarjeta_ultimos4: str | None = None
    tarjeta_marca: str | None = None


class ProveedorPago(ABC):
    @abstractmethod
    async def cobrar(self, solicitud: SolicitudCobro) -> ResultadoCobro:
        raise NotImplementedError


class ProveedorTarjeta(ProveedorPago):
    @abstractmethod
    async def tokenizar(self, tarjeta: DatosTarjeta, correlation_id: str) -> str:
        raise NotImplementedError
