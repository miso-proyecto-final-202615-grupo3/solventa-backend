from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EventoTrazabilidadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evento_id: UUID
    cotizacion_id: UUID
    cliente_id: UUID
    tipo: str
    ocurrido_en: datetime
    origen: str
    actor_id: str | None
    resultado: str
    referencia_id: str
    correlation_id: str | None
    detalles: dict[str, Any] = Field(default_factory=dict)


class TrazabilidadEmisionResponse(BaseModel):
    poliza_id: UUID
    numero: str
    cotizacion_id: UUID
    cliente_id: UUID
    eventos: list[EventoTrazabilidadResponse]
