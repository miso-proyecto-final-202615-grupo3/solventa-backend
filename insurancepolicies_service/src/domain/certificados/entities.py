import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

RUTA_BASE_CERTIFICADOS = "certificados-poliza"
NOMBRE_ARCHIVO_CERTIFICADO = "certificado-poliza.pdf"
PLANTILLA_CERTIFICADO = "certificado_poliza.html"


class EstadoGeneracion(StrEnum):
    EN_PROCESO = "EN_PROCESO"
    GENERADO = "GENERADO"
    FALLIDO = "FALLIDO"


def construir_ruta_certificado(cliente_id: uuid.UUID, poliza_id: uuid.UUID) -> str:
    """Ruta relativa, igual en disco local y en S3."""
    return f"{RUTA_BASE_CERTIFICADOS}/{cliente_id}/{poliza_id}/{NOMBRE_ARCHIVO_CERTIFICADO}"


@dataclass
class GeneracionCertificado:
    """Un intento de generar el certificado PDF de una póliza (auditoría, una fila por intento)."""

    poliza_id: uuid.UUID
    cliente_id: uuid.UUID
    plantilla: str
    datos_plantilla: dict[str, Any]
    iniciada_en: datetime
    correlation_id: str
    estado: EstadoGeneracion = EstadoGeneracion.EN_PROCESO
    finalizada_en: datetime | None = None
    ruta_certificado: str | None = None
    error_codigo: str | None = None
    error_detalle: str | None = None
    generacion_id: uuid.UUID = field(default_factory=uuid.uuid4)
