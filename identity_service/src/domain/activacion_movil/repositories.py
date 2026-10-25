from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from src.domain.activacion_movil.entities import (
    DatosDispositivo,
    EstadoIntento,
    IntentoPruebaVida,
    SesionActivacion,
)


class ActivacionMovilRepository(ABC):
    @abstractmethod
    async def dispositivo_esta_vinculado(
        self, cliente_id: UUID, installation_id: UUID
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def obtener_sesion_creada(
        self, installation_id: UUID
    ) -> SesionActivacion | None:
        raise NotImplementedError

    @abstractmethod
    async def guardar_sesion(self, sesion: SesionActivacion) -> None:
        raise NotImplementedError

    @abstractmethod
    async def cancelar_sesion(self, sesion_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def contar_intentos_consumidos(
        self, cliente_id: UUID, desde: datetime
    ) -> int:
        raise NotImplementedError

    @abstractmethod
    async def guardar_intento(self, intento: IntentoPruebaVida) -> None:
        raise NotImplementedError

    @abstractmethod
    async def actualizar_estado_intento(
        self,
        intento_id: UUID,
        estado: EstadoIntento,
        resuelto_en: datetime | None = None,
        folio: str | None = None,
        motivo: str | None = None,
    ) -> None:
        raise NotImplementedError
