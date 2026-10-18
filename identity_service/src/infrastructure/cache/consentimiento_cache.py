import json
import uuid
from json import JSONDecodeError
from typing import Any

from redis.asyncio import Redis

from src.application.ports.consentimiento_cache import ConsentimientoCacheEntry
from src.domain.consentimiento.entities import EstadoConsentimiento


class ConsentimientoCache:
    def __init__(self, redis: Redis, ttl_seconds: int = 300) -> None:
        self.redis = redis
        self.ttl_seconds = min(max(ttl_seconds, 1), 300)

    @staticmethod
    def _key(cliente_id: uuid.UUID) -> str:
        return f"identity:consentimiento:{cliente_id}"

    async def obtener(
        self, cliente_id: uuid.UUID
    ) -> ConsentimientoCacheEntry | None:
        key = self._key(cliente_id)
        value = await self.redis.get(key)
        if value is None:
            return None
        try:
            payload: dict[str, Any] = json.loads(value)
            entry = ConsentimientoCacheEntry(
                estado=EstadoConsentimiento(payload["estado"]),
                perfil=payload.get("perfil"),
            )
        except (JSONDecodeError, KeyError, TypeError, ValueError):
            await self.redis.delete(key)
            return None
        return entry

    async def guardar(
        self,
        cliente_id: uuid.UUID,
        estado: EstadoConsentimiento,
        perfil: dict[str, Any] | None,
    ) -> None:
        payload = json.dumps({"estado": estado.value, "perfil": perfil})
        await self.redis.set(self._key(cliente_id), payload, ex=self.ttl_seconds)

    async def invalidar(self, cliente_id: uuid.UUID) -> None:
        await self.redis.delete(self._key(cliente_id))

    async def cerrar(self) -> None:
        await self.redis.aclose()