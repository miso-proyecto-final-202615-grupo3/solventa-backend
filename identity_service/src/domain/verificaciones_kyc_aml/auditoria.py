import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class EventoTrazabilidadKycAml:
    cotizacion_id: uuid.UUID
    cliente_id: uuid.UUID
    tipo: str
    ocurrido_en: datetime
    origen: str
    resultado: str
    referencia_id: str
    correlation_id: str | None = None
    actor_id: str | None = None
    detalles: dict[str, Any] = field(default_factory=dict)
    evento_id: uuid.UUID = field(default_factory=uuid.uuid4)
