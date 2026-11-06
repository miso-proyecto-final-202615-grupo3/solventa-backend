import uuid
from abc import ABC, abstractmethod

from src.domain.pagos.entities import Pago


class PagoRepository(ABC):
    @abstractmethod
    async def guardar(self, pago: Pago) -> Pago:
        raise NotImplementedError

    @abstractmethod
    async def obtener_por_id(self, pago_id: uuid.UUID) -> Pago | None:
        raise NotImplementedError
