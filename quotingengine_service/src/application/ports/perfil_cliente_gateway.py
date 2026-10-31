import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date


class PerfilClienteError(Exception):
    pass


class ClienteNoEncontradoError(PerfilClienteError):
    pass


class ConsentimientoNoOtorgadoError(PerfilClienteError):
    """El cliente no autorizó el uso de sus datos: se cotiza sin personalizar."""


class PerfilNoDisponibleError(PerfilClienteError):
    """Timeout, circuito abierto, bulkhead lleno o falla del servicio de identidad."""


@dataclass(frozen=True)
class PerfilCliente:
    cliente_id: uuid.UUID
    nombres: str
    apellidos: str
    tipo_documento: str
    numero_identificacion: str
    correo: str
    fecha_nacimiento: date | None
    pais_residencia: str
    telefono: str
    estado_kyc: str


class PerfilClienteGateway(ABC):
    @abstractmethod
    async def obtener_perfil(self, cliente_id: uuid.UUID) -> PerfilCliente:
        raise NotImplementedError
