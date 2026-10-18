from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.domain.consentimiento.entities import EstadoConsentimiento


class ConsentimientoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cliente_id: UUID
    estado: EstadoConsentimiento
    otorgado_en: datetime | None
    revocado_en: datetime | None


class ActualizarConsentimientoRequest(BaseModel):
    estado: EstadoConsentimiento