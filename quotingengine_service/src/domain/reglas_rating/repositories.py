import uuid
from abc import ABC, abstractmethod

from src.domain.reglas_rating.entities import ReglaRating


class ReglaRatingRepository(ABC):
    @abstractmethod
    async def guardar(self, regla: ReglaRating) -> ReglaRating:
        raise NotImplementedError

    @abstractmethod
    async def obtener_vigente_por_producto(
        self, producto_id: uuid.UUID
    ) -> ReglaRating | None:
        raise NotImplementedError

    @abstractmethod
    async def obtener_vigentes_por_productos(
        self, producto_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, ReglaRating]:
        raise NotImplementedError

    @abstractmethod
    async def existe_por_producto(self, producto_id: uuid.UUID) -> bool:
        raise NotImplementedError
