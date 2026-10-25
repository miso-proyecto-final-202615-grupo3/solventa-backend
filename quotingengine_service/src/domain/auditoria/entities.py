import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class AuditoriaDecision:
    cotizacion_id: uuid.UUID
    regla_rating_id: uuid.UUID
    tipo_decision: str
    entradas: dict[str, Any]
    resultado: dict[str, Any]
    decidida_en: datetime | None = None
    auditoria_decision_id: uuid.UUID = field(default_factory=uuid.uuid4)
