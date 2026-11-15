import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from src.domain.certificados.entities import EstadoGeneracion
from src.domain.polizas.entities import EstadoCertificado


class ResumenPolizaResponse(BaseModel):
    poliza_id: uuid.UUID
    numero: str
    estado: str
    cotizacion_id: uuid.UUID
    titular_nombre: str
    vigencia_desde: datetime
    vigencia_hasta: datetime
    prima: Decimal
    moneda: str | None
    estado_certificado: EstadoCertificado


class GeneracionCertificadoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    estado: EstadoGeneracion
    plantilla: str
    iniciada_en: datetime
    finalizada_en: datetime | None
    error_codigo: str | None


class EstadoCertificadoResponse(BaseModel):
    poliza_id: uuid.UUID
    estado_certificado: EstadoCertificado
    disponible: bool
    ultima_generacion: GeneracionCertificadoResponse | None


class EventoTrazabilidadPolizaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    evento_id: uuid.UUID
    cotizacion_id: uuid.UUID
    cliente_id: uuid.UUID
    tipo: str
    ocurrido_en: datetime
    origen: str
    actor_id: str | None
    resultado: str
    referencia_id: str
    correlation_id: str | None
    detalles: dict[str, Any]


class HistorialPolizaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tipo: str
    ocurrido_en: datetime
    resultado: str


class ReferenciaTrazabilidadPolizaResponse(BaseModel):
    poliza_id: uuid.UUID
    numero: str
    cotizacion_id: uuid.UUID
    cliente_id: uuid.UUID
    eventos: list[EventoTrazabilidadPolizaResponse]
