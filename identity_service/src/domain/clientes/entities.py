import uuid
from dataclasses import dataclass, field
from datetime import date, datetime

from src.domain.clientes.value_objects import EstadoKYC


@dataclass(frozen=True)
class ClienteId:
    value: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class Cliente:
    id: ClienteId
    nombres: str
    apellidos: str
    tipo_documento: str
    numero_identificacion: str
    correo: str
    fecha_nacimiento: date
    pais_residencia: str
    telefono: str
    estado_kyc: EstadoKYC = EstadoKYC.PENDIENTE
    fecha_creacion: datetime | None = None
    fecha_actualizacion: datetime | None = None