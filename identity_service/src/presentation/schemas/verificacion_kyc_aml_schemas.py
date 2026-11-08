from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel


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
