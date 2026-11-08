import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from src.domain.condiciones.entities import Decision


class CondicionesResponse(BaseModel):
    condiciones_cotizacion_id: uuid.UUID
    cotizacion_id: uuid.UUID
    version_condiciones_generales: str
    condiciones_generales: str
    condiciones_particulares: dict[str, Any]
    creada_en: datetime
    ultima_decision: "DecisionResponse | None" = None


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    condiciones_cotizacion_id: uuid.UUID
    decision: Decision


class DecisionResponse(BaseModel):
    decision_condiciones_id: uuid.UUID
    condiciones_cotizacion_id: uuid.UUID
    cliente_id: uuid.UUID
    version_condiciones_generales: str
    decision: Decision
    decidida_en: datetime
