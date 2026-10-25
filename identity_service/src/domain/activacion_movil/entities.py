import uuid
from dataclasses import dataclass
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
