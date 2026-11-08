import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class Decision(StrEnum):
    ACEPTADA = "ACEPTADA"
    RECHAZADA = "RECHAZADA"


@dataclass
class CondicionesCotizacion:
    cotizacion_id: uuid.UUID
    version_condiciones_generales: str
    condiciones_generales: str
    condiciones_particulares: dict[str, Any]
    condiciones_cotizacion_id: uuid.UUID = field(default_factory=uuid.uuid4)
    creada_en: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class DecisionCondiciones:
    condiciones_cotizacion_id: uuid.UUID
    cliente_id: uuid.UUID
    decision: Decision
    decision_condiciones_id: uuid.UUID = field(default_factory=uuid.uuid4)
    decidida_en: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
