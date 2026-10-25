import hashlib
import json
from typing import Any

from redis.asyncio import Redis

from src.application.ports.perfilamiento import OpenDataCachePort
from src.domain.open_data import CategoriaOpenData, PerfilTerritorial


class OpenDataRedisCache(OpenDataCachePort):
    def __init__(self, redis: Redis, ttl_seconds: int = 300) -> None:
        self.redis = redis
        self.ttl_seconds = min(max(ttl_seconds, 1), 86400)

    @staticmethod
    def _key(ubicacion: dict[str, Any]) -> str:
        encoded = json.dumps(
            ubicacion, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        return f"motor-cotizacion:open-data:{digest}"

    async def obtener(
        self, ubicacion: dict[str, Any]
    ) -> CategoriaOpenData | None:
        key = self._key(ubicacion)
        value = await self.redis.get(key)
        if value is None:
            return None
        try:
            payload = json.loads(value)
            return CategoriaOpenData(payload["categoria"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            await self.redis.delete(key)
            return None

    async def guardar(
        self, ubicacion: dict[str, Any], perfil: PerfilTerritorial
    ) -> None:
        value = json.dumps({"categoria": perfil.categoria.value})
        await self.redis.set(self._key(ubicacion), value, ex=self.ttl_seconds)
