from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.domain.consentimiento.entities import EstadoConsentimiento


class ClienteAuditadoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nombres: str
    apellidos: str
    tipo_documento: str
    numero_identificacion: str
    correo: str
    estado_consentimiento: EstadoConsentimiento | None


class EventoAuditoriaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tipo_accion: str
    fecha: datetime
    version_terminos: str
    canal: str


class AuditoriaConsentimientoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cliente: ClienteAuditadoResponse
    eventos: list[EventoAuditoriaResponse]
