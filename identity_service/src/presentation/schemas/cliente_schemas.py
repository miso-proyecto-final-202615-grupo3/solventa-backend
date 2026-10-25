import re
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from src.domain.clientes.value_objects import EstadoKYC, TipoDocumento
from src.domain.activacion_movil.entities import Plataforma

_PHONE_PATTERN = re.compile(r"^\+?[0-9][0-9\s\-()]{6,19}$")
_CEDULA_PATTERN = re.compile(r"^\d{5,10}$")
EDAD_MINIMA = 18


class ClienteCreate(BaseModel):
    """Payload de registro de un nuevo cliente asegurado."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    nombres: str = Field(min_length=1, max_length=100)
    apellidos: str = Field(min_length=1, max_length=100)
    tipo_documento: TipoDocumento = TipoDocumento.CC
    numero_identificacion: str = Field(min_length=5, max_length=30)
    correo: EmailStr
    password: str = Field(min_length=8, max_length=128)
    consentimiento_datos: bool = False
    fecha_nacimiento: date
    pais_residencia: str = Field(min_length=2, max_length=60)
    telefono: str = Field(min_length=7, max_length=20)

    @field_validator("fecha_nacimiento")
    @classmethod
    def _fecha_nacimiento_en_pasado(cls, value: date) -> date:
        if value >= date.today():
            raise ValueError(
                "La fecha de nacimiento debe ser anterior a la fecha actual."
            )
        return value

    @field_validator("fecha_nacimiento")
    @classmethod
    def _mayor_de_edad(cls, value: date) -> date:
        hoy = date.today()
        edad = hoy.year - value.year - (
            (hoy.month, hoy.day) < (value.month, value.day)
        )
        if edad < EDAD_MINIMA:
            raise ValueError(
                f"Debes ser mayor de {EDAD_MINIMA} años para crear una cuenta."
            )
        return value

    @field_validator("numero_identificacion")
    @classmethod
    def _cedula_numerica(cls, value: str) -> str:
        if not _CEDULA_PATTERN.match(value):
            raise ValueError(
                "El número de identificación debe tener solo dígitos, entre 5 y 10."
            )
        return value

    @field_validator("telefono")
    @classmethod
    def _telefono_valido(cls, value: str) -> str:
        if not _PHONE_PATTERN.match(value):
            raise ValueError(
                "El teléfono debe contener solo dígitos, espacios, '+', '-' o paréntesis."
            )
        return value


class ClienteResponse(BaseModel):
    """Datos del cliente expuestos por la API (nunca incluye el password)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nombres: str
    apellidos: str
    tipo_documento: TipoDocumento
    numero_identificacion: str
    correo: EmailStr
    fecha_nacimiento: date
    pais_residencia: str
    telefono: str
    estado_kyc: EstadoKYC
    fecha_creacion: datetime
    fecha_actualizacion: datetime


class IniciarActivacionMovilRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    correo: EmailStr
    installation_id: UUID
    plataforma: Plataforma
    modelo: str = Field(min_length=1, max_length=100)
    version_so: str = Field(min_length=1, max_length=20)


class IniciarActivacionMovilResponse(BaseModel):
    dispositivo_vinculado: bool
    sesion_id: str | None = None
    expira_en: datetime | None = None
    captura: dict | None = None
    intentos_restantes: int | None = None
