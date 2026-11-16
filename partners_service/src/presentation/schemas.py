from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.domain.socios.entities import EstadoSocio, Socio


class RegistrarSocioRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    nombre: str = Field(min_length=1, max_length=120)
    tipo_socio: str = Field(min_length=1, max_length=60)
    canal_integracion: str = Field(min_length=1, max_length=60)

    @field_validator("nombre", "tipo_socio", "canal_integracion")
    @classmethod
    def no_acepta_solo_espacios(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("El campo no puede estar vacío.")
        return value


class SocioResponse(BaseModel):
    id: UUID
    nombre: str
    tipo_socio: str
    canal_integracion: str
    estado: EstadoSocio
    creado_en: datetime

    @classmethod
    def desde_entidad(cls, socio: Socio) -> "SocioResponse":
        return cls(
            id=socio.id,
            nombre=socio.nombre,
            tipo_socio=socio.tipo_socio,
            canal_integracion=socio.canal_integracion,
            estado=socio.estado,
            creado_en=socio.creado_en,
        )
