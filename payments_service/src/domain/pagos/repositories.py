import uuid
from abc import ABC, abstractmethod

from src.domain.pagos.entities import PagoPrima


class PagoDuplicadoError(Exception):
    """Viola una restricción de unicidad: misma clave de idempotencia o pago activo de la cotización."""


class PagoPrimaRepository(ABC):
    @abstractmethod
    async def crear(self, pago: PagoPrima) -> None:
        """Inserta el pago; lanza PagoDuplicadoError si viola una restricción de unicidad."""
        raise NotImplementedError

    @abstractmethod
    async def obtener_por_id(self, pago_id: uuid.UUID) -> PagoPrima | None:
        raise NotImplementedError

    @abstractmethod
    async def obtener_por_idempotency_key(
        self, cliente_id: uuid.UUID, idempotency_key: str
    ) -> PagoPrima | None:
        raise NotImplementedError

    @abstractmethod
    async def obtener_activo_por_cotizacion(self, cotizacion_id: uuid.UUID) -> PagoPrima | None:
        """Pago PENDIENTE, APROBADO o en ERROR de la cotización (ver ESTADOS_PAGO_ACTIVO)."""
        raise NotImplementedError

    @abstractmethod
    async def actualizar(self, pago: PagoPrima) -> bool:
        """Actualiza con control optimista de versión; False si otro proceso lo modificó antes."""
        raise NotImplementedError
