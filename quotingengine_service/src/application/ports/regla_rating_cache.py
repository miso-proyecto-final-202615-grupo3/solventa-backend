import uuid
from typing import Protocol

from src.domain.reglas_rating.entities import ReglaRating


class ReglaRatingCachePort(Protocol):
    async def obtener(self, producto_id: uuid.UUID) -> ReglaRating | None: ...

    async def guardar(self, regla: ReglaRating) -> None: ...

    async def invalidar(self, producto_id: uuid.UUID) -> None: ...
