import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass
class Pago:
    poliza_id: uuid.UUID
    tipo: str
    monto: Decimal
    moneda: str
    estado: str
    clave_idempotencia: str
    indemnizacion_id: uuid.UUID | None = None
    procesado_en: datetime | None = None
    pago_id: uuid.UUID = field(default_factory=uuid.uuid4)
