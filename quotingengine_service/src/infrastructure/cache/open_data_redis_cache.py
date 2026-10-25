import hashlib
import json
from typing import Any

from redis.asyncio import Redis

from src.application.ports.open_data_gateway import OpenDataCachePort
from src.domain.open_data import CategoriaOpenData, PerfilTerritorial


class OpenDataRedisCache(OpenDataCachePort):
    def __init__(self, redis: Redis, ttl_seconds: int = 300) -> None:
        self._redis = redis
        self._ttl = min(max(ttl_seconds, 1), 86400)

    async def obtener(self, ubicacion: dict[str, Any]) -> CategoriaOpenData | None:
        key = self._key(ubicacion)
        value = await self._redis.get(key)
        if value is None:
            return None
        try:
            return CategoriaOpenData(json.loads(value)["categoria"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            await self._redis.delete(key)
            return None

    async def guardar(
        self, ubicacion: dict[str, Any], perfil: PerfilTerritorial
    ) -> None:
        await self._redis.set(
            self._key(ubicacion),
            json.dumps({"categoria": perfil.categoria.value}),
            ex=self._ttl,
        )

    @staticmethod
    def _key(ubicacion: dict[str, Any]) -> str:
        value = json.dumps(ubicacion, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
        return f"quotingengine:open-data:{digest}"
