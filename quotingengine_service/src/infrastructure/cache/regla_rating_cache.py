import json
import logging
import uuid
from datetime import datetime
from json import JSONDecodeError

from redis.asyncio import Redis
from redis.exceptions import RedisError

from src.domain.reglas_rating.entities import EstadoReglaRating, ReglaRating

logger = logging.getLogger(__name__)


class ReglaRatingCache:
    """Caché de reglas de rating vigentes en Redis.

    Si Redis falla se degrada a "sin caché": la regla se lee de la base de datos.
    """

    def __init__(self, redis: Redis, ttl_seconds: int = 300) -> None:
        self.redis = redis
        self.ttl_seconds = max(ttl_seconds, 1)

    @staticmethod
    def _key(producto_id: uuid.UUID) -> str:
        return f"quotingengine:regla_rating:{producto_id}"

    async def obtener(self, producto_id: uuid.UUID) -> ReglaRating | None:
        key = self._key(producto_id)
        try:
            value = await self.redis.get(key)
            if value is None:
                return None
            payload = json.loads(value)
            return ReglaRating(
                regla_rating_id=uuid.UUID(payload["regla_rating_id"]),
                producto_id=uuid.UUID(payload["producto_id"]),
                version=payload["version"],
                estado=EstadoReglaRating(payload["estado"]),
                definicion=payload["definicion"],
                vigente_desde=datetime.fromisoformat(payload["vigente_desde"]),
                vigente_hasta=(
                    datetime.fromisoformat(payload["vigente_hasta"])
                    if payload.get("vigente_hasta")
                    else None
                ),
            )
        except RedisError:
            logger.warning("Caché de reglas no disponible", exc_info=True)
            return None
        except (JSONDecodeError, KeyError, TypeError, ValueError):
            await self._borrar_silencioso(key)
            return None

    async def guardar(self, regla: ReglaRating) -> None:
        payload = json.dumps(
            {
                "regla_rating_id": str(regla.regla_rating_id),
                "producto_id": str(regla.producto_id),
                "version": regla.version,
                "estado": regla.estado.value,
                "definicion": regla.definicion,
                "vigente_desde": regla.vigente_desde.isoformat(),
                "vigente_hasta": (
                    regla.vigente_hasta.isoformat() if regla.vigente_hasta else None
                ),
            }
        )
        try:
            await self.redis.set(
                self._key(regla.producto_id), payload, ex=self.ttl_seconds
            )
        except RedisError:
            logger.warning("No se pudo guardar la regla en caché", exc_info=True)

    async def invalidar(self, producto_id: uuid.UUID) -> None:
        await self._borrar_silencioso(self._key(producto_id))

    async def cerrar(self) -> None:
        await self.redis.aclose()

    async def _borrar_silencioso(self, key: str) -> None:
        try:
            await self.redis.delete(key)
        except RedisError:
            logger.warning("No se pudo invalidar la caché de reglas", exc_info=True)
