from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EstadoValidacion(str, Enum):
    INICIADA = "INICIADA"


class EstadoResultadoVerificacion(str, Enum):
    APROBADO = "APROBADO"
    RECHAZADO = "RECHAZADO"
    PENDIENTE = "PENDIENTE"


class IniciarVerificacionKycAmlResponse(BaseModel):
    verificacion_id: UUID
    estado: EstadoValidacion
    fecha: datetime


class VerificacionKycAmlResponse(BaseModel):
    verificacion_id: UUID
    cliente_id: UUID
    resultado_kyc: EstadoResultadoVerificacion
    resultado_aml: EstadoResultadoVerificacion
    estado: EstadoResultadoVerificacion
    fecha_resultado: datetime | None = None


class EventoTrazabilidadKycAmlResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    detalles: dict[str, Any]
