import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Plataforma(StrEnum):
    ANDROID = "ANDROID"
    IOS = "IOS"


class EstadoSesion(StrEnum):
    CREADA = "CREADA"
    EN_VERIFICACION = "EN_VERIFICACION"
    USADA = "USADA"
    CANCELADA = "CANCELADA"


class EstadoIntento(StrEnum):
    EN_CURSO = "EN_CURSO"
    APROBADO = "APROBADO"
    RECHAZADO = "RECHAZADO"
    ANULADO = "ANULADO"


class EstadoDispositivo(StrEnum):
    ACTIVO = "ACTIVO"
    REVOCADO = "REVOCADO"


@dataclass(frozen=True)
class DatosDispositivo:
    installation_id: uuid.UUID
    plataforma: Plataforma
    modelo: str
    version_so: str


@dataclass(frozen=True)
class SesionActivacion:
    id: str
    cliente_id: uuid.UUID
    dispositivo: DatosDispositivo
    tipo_captura: str
    estado: EstadoSesion
    creada_en: datetime
    expira_en: datetime


@dataclass(frozen=True)
class IntentoPruebaVida:
    id: uuid.UUID
    cliente_id: uuid.UUID
    sesion_id: str
    installation_id: uuid.UUID
    estado: EstadoIntento
    creado_en: datetime
    folio: str | None = None
    motivo: str | None = None
    resuelto_en: datetime | None = None
