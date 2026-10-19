import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from src.domain.consentimiento.entities import EstadoConsentimiento


@dataclass(frozen=True)
class ClienteAuditado:
    id: uuid.UUID
    nombres: str
    apellidos: str
    tipo_documento: str
    numero_identificacion: str
    correo: str
    estado_consentimiento: EstadoConsentimiento | None


@dataclass(frozen=True)
class EventoAuditoriaConsentimiento:
    id: uuid.UUID
    tipo_accion: str
    fecha: datetime
    version_terminos: str
    canal: str


@dataclass(frozen=True)
class AuditoriaConsentimiento:
    cliente: ClienteAuditado
    eventos: list[EventoAuditoriaConsentimiento]


class AuditoriaConsentimientoRepository(ABC):
    """Consulta de solo lectura del log de auditoría de consentimientos."""

    @abstractmethod
    async def buscar_por_correo(
        self, correo: str
    ) -> AuditoriaConsentimiento | None:
        raise NotImplementedError

    @abstractmethod
    async def buscar_por_identificacion(
        self, numero_identificacion: str
    ) -> AuditoriaConsentimiento | None:
        raise NotImplementedError
