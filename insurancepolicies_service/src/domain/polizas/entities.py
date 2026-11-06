import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass
class PolizaCobertura:
    poliza_id: uuid.UUID
    cobertura_id: uuid.UUID
    limite_asegurado: Decimal
    deducible: Decimal
    prima: Decimal
    poliza_cobertura_id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class Poliza:
    cliente_id: uuid.UUID
    cotizacion_id: uuid.UUID
    producto_id: uuid.UUID
    numero: str
    estado: str
    vigencia_desde: datetime
    vigencia_hasta: datetime
    emitida_en: datetime | None = None
    poliza_id: uuid.UUID = field(default_factory=uuid.uuid4)
    coberturas: list[PolizaCobertura] = field(default_factory=list)
