import uuid
from datetime import datetime
from decimal import Decimal

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
