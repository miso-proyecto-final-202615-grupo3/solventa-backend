import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class MetodoPago(StrEnum):
    PAYPAL = "PAYPAL"
    TARJETA_CREDITO = "TARJETA_CREDITO"


METODO_PAGO_DEFECTO = MetodoPago.PAYPAL


class EstadoPago(StrEnum):
    PENDIENTE = "PENDIENTE"
    APROBADO = "APROBADO"
    RECHAZADO = "RECHAZADO"
    ERROR = "ERROR"


# Estados que bloquean otro intento de pago de la misma cotización: un pago PENDIENTE o en ERROR
# puede haber cobrado sin que lo sepamos y solo se resuelve reintentando con la misma clave.
ESTADOS_PAGO_ACTIVO = (EstadoPago.PENDIENTE, EstadoPago.APROBADO, EstadoPago.ERROR)


@dataclass
class PagoPrima:
    """Pago de la prima inicial de una cotización (HU1.3.4)."""

    cotizacion_id: uuid.UUID
    cliente_id: uuid.UUID
    monto: Decimal
    moneda: str
    metodo_pago: MetodoPago
    proveedor: str
    idempotency_key: str
    hash_solicitud: str
    correlation_id: str
    creado_en: datetime
    actualizado_en: datetime
    estado: EstadoPago = EstadoPago.PENDIENTE
    proveedor_referencia: str | None = None
    codigo_rechazo: str | None = None
    error_codigo: str | None = None
    tarjeta_ultimos4: str | None = None
    tarjeta_marca: str | None = None
    procesado_en: datetime | None = None
    version: int = 1
    pago_id: uuid.UUID = field(default_factory=uuid.uuid4)
