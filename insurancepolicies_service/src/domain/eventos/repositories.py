import uuid
from abc import ABC, abstractmethod

from src.domain.eventos.trazabilidad import EventoTrazabilidadPoliza
from datetime import datetime

from src.domain.eventos.entities import EventoOutbox


class EventoOutboxRepository(ABC):
    @abstractmethod
    async def agregar(self, evento: EventoOutbox) -> None:
        """Registra el evento en la transacción en curso, sin confirmarla."""
        raise NotImplementedError

    @abstractmethod
    async def obtener_pendientes(self, limite: int) -> list[EventoOutbox]:
        """Eventos sin publicar, del más antiguo al más reciente, bloqueados para este proceso."""
        raise NotImplementedError

    @abstractmethod
    async def marcar_publicado(self, evento_id: uuid.UUID, cuando: datetime) -> None:
        raise NotImplementedError

    @abstractmethod
    async def registrar_fallo(self, evento_id: uuid.UUID, detalle: str) -> None:
        raise NotImplementedError


class AuditoriaPolizaRepository(ABC):
    @abstractmethod
    async def agregar(self, evento: EventoTrazabilidadPoliza) -> None:
        raise NotImplementedError

    @abstractmethod
    async def listar_por_cotizacion(
        self, cotizacion_id: uuid.UUID
    ) -> list[EventoTrazabilidadPoliza]:
        raise NotImplementedError
