import uuid

from src.application.ports.regla_rating_cache import ReglaRatingCachePort
from src.domain.reglas_rating.entities import ReglaRating
from src.domain.reglas_rating.repositories import ReglaRatingRepository


class ReglaRatingResolver:
    """Resuelve la regla de rating vigente: caché primero, base de datos como respaldo."""

    def __init__(
        self, repository: ReglaRatingRepository, cache: ReglaRatingCachePort
    ) -> None:
        self.repository = repository
        self.cache = cache

    async def obtener_vigente(self, producto_id: uuid.UUID) -> ReglaRating | None:
        regla = await self.cache.obtener(producto_id)
        if regla is not None:
            return regla
        regla = await self.repository.obtener_vigente_por_producto(producto_id)
        if regla is not None:
            await self.cache.guardar(regla)
        return regla

    async def obtener_vigentes(
        self, producto_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, ReglaRating]:
        reglas: dict[uuid.UUID, ReglaRating] = {}
        faltantes: list[uuid.UUID] = []
        for producto_id in producto_ids:
            regla = await self.cache.obtener(producto_id)
            if regla is None:
                faltantes.append(producto_id)
            else:
                reglas[producto_id] = regla
        for producto_id, regla in (
            await self.repository.obtener_vigentes_por_productos(faltantes)
        ).items():
            await self.cache.guardar(regla)
            reglas[producto_id] = regla
        return reglas
