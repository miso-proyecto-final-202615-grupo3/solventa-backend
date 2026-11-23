from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4


class EstadoSocio(StrEnum):
    PENDIENTE = "PENDIENTE"
    ACTIVO = "ACTIVO"
    RECHAZADO = "RECHAZADO"


@dataclass(frozen=True)
class Socio:
    id: UUID
    nombre: str
    correo: str
    tipo_socio: str
    canal_integracion: str
    estado: EstadoSocio
    creado_en: datetime
    registrado_por: str

    @classmethod
    def registrar(
        cls,
        nombre: str,
        correo: str,
        tipo_socio: str,
        canal_integracion: str,
        registrado_por: str,
        creado_en: datetime,
    ) -> tuple["Socio", "EventoSocio"]:
        socio_id = uuid4()
        socio = cls(
            id=socio_id,
            nombre=nombre.strip(),
            correo=correo.strip().lower(),
            tipo_socio=tipo_socio.strip(),
            canal_integracion=canal_integracion.strip(),
            estado=EstadoSocio.ACTIVO,
            creado_en=creado_en,
            registrado_por=registrado_por,
        )
        return socio, EventoSocio(
            id=uuid4(),
            socio_id=socio_id,
            accion="REGISTRO",
            actor_id=registrado_por,
            ocurrido_en=creado_en,
        )


@dataclass(frozen=True)
class EventoSocio:
    id: UUID
    socio_id: UUID
    accion: str
    actor_id: str
    ocurrido_en: datetime
