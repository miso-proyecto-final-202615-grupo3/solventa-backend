import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class EstadoEvento(StrEnum):
    PENDIENTE = "PENDIENTE"
    PUBLICADO = "PUBLICADO"


@dataclass
class EventoOutbox:
    """Mensaje que se guarda con la transacción de negocio y se publica después en el bus."""

    tipo: str
    agregado_id: uuid.UUID
    payload: dict[str, Any]
    creado_en: datetime
    estado: EstadoEvento = EstadoEvento.PENDIENTE
    intentos: int = 0
    ultimo_error: str | None = None
    publicado_en: datetime | None = None
    evento_id: uuid.UUID = field(default_factory=uuid.uuid4)
