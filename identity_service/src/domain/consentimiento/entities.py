import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class EstadoConsentimiento(StrEnum):
    ACEPTADO = "ACEPTADO"
    REVOCADO = "REVOCADO"


class TipoAccionConsentimiento(StrEnum):
    ACEPTACION = "ACEPTACION"
    DENEGACION = "DENEGACION"
    REVOCACION = "REVOCACION"


@dataclass(frozen=True)
class ConsentimientoInicial:
    estado: EstadoConsentimiento
    tipo_accion: TipoAccionConsentimiento
    fecha: datetime
    version_terminos: str
    canal: str


@dataclass(frozen=True)
class ConsentimientoActual:
    cliente_id: uuid.UUID
    estado: EstadoConsentimiento
    otorgado_en: datetime | None
    revocado_en: datetime | None