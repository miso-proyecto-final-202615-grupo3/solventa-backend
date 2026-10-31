import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class EstadoCotizacion(StrEnum):
    VIGENTE = "VIGENTE"
    EXPIRADA = "EXPIRADA"


@dataclass
class CotizacionCobertura:
    cotizacion_id: uuid.UUID
    cobertura_id: uuid.UUID
    prima: Decimal
    limite_asegurado: Decimal
    deducible: Decimal
    cotizacion_cobertura_id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class Cotizacion:
    cliente_id: uuid.UUID
    producto_id: uuid.UUID
    prima_total: Decimal
    moneda: str
    expira_en: datetime
    estado: EstadoCotizacion = EstadoCotizacion.VIGENTE
    socio_id: uuid.UUID | None = None
    perfil_riesgo_id: uuid.UUID | None = None
    creada_en: datetime | None = None
    cotizacion_id: uuid.UUID = field(default_factory=uuid.uuid4)
