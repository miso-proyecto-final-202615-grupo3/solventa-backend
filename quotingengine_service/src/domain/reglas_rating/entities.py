import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class EstadoReglaRating(StrEnum):
    VIGENTE = "VIGENTE"
    OBSOLETA = "OBSOLETA"


@dataclass
class ReglaRating:
    producto_id: uuid.UUID
    version: str
    definicion: dict[str, Any]
    vigente_desde: datetime
    estado: EstadoReglaRating = EstadoReglaRating.VIGENTE
    vigente_hasta: datetime | None = None
    regla_rating_id: uuid.UUID = field(default_factory=uuid.uuid4)
