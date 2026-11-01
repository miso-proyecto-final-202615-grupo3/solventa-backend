import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


class PerfilClienteError(Exception):
    pass


class ClienteNoEncontradoError(PerfilClienteError):
    pass


class ConsentimientoNoOtorgadoError(PerfilClienteError):
    """El cliente no autorizó el uso de sus datos financieros."""


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
    open_finance_disponible: bool = True
    ingreso_mensual: Decimal | None = None
    ahorros_liquidos: Decimal | None = None
    dti_pct: Decimal | None = None
    sobregiros_12_meses: int | None = None
    score: int | None = None


class PerfilClienteGateway(ABC):
    @abstractmethod
    async def obtener_perfil(self, cliente_id: uuid.UUID) -> PerfilCliente:
        raise NotImplementedError
