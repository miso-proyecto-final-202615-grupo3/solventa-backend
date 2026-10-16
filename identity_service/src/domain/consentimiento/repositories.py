import uuid
from abc import ABC, abstractmethod

from src.domain.consentimiento.entities import (
    ConsentimientoActual,
    EstadoConsentimiento,
)


class ConsentimientoRepository(ABC):
    @abstractmethod
    async def obtener_actual(
        self, cliente_id: uuid.UUID
    ) -> ConsentimientoActual | None:
        raise NotImplementedError

    @abstractmethod
    async def actualizar_estado(
        self,
        cliente_id: uuid.UUID,
        estado: EstadoConsentimiento,
        version_terminos: str,
        canal: str,
    ) -> ConsentimientoActual | None:
        raise NotImplementedError