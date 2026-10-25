import json
import uuid
from datetime import datetime, timezone

from src.domain.reglas_rating.entities import ReglaRating
from src.infrastructure.cache.regla_rating_cache import ReglaRatingCache
from tests.fakes import FakeRedis


def _regla() -> ReglaRating:
    return ReglaRating(
        producto_id=uuid.uuid4(),
        version="1.0",
        definicion={"tasa_base": "0.1"},
        vigente_desde=datetime.now(timezone.utc),
    )


async def test_guardar_y_obtener():
    redis = FakeRedis()
    cache = ReglaRatingCache(redis, ttl_seconds=60)
    regla = _regla()

    await cache.guardar(regla)
    obtenida = await cache.obtener(regla.producto_id)

    assert obtenida == regla
    assert redis.ttls[f"quotingengine:regla_rating:{regla.producto_id}"] == 60


async def test_obtener_sin_entrada_retorna_none():
    assert await ReglaRatingCache(FakeRedis()).obtener(uuid.uuid4()) is None


async def test_invalidar():
    cache = ReglaRatingCache(FakeRedis())
    regla = _regla()
    await cache.guardar(regla)

    await cache.invalidar(regla.producto_id)

    assert await cache.obtener(regla.producto_id) is None


async def test_entrada_corrupta_se_descarta():
    redis = FakeRedis()
    cache = ReglaRatingCache(redis)
    producto_id = uuid.uuid4()
    key = f"quotingengine:regla_rating:{producto_id}"
    redis.data[key] = json.dumps({"x": 1})

    assert await cache.obtener(producto_id) is None
    assert key not in redis.data


async def test_redis_caido_degrada_sin_cache():
    cache = ReglaRatingCache(FakeRedis(fallar=True))
    regla = _regla()

    await cache.guardar(regla)
    await cache.invalidar(regla.producto_id)

    assert await cache.obtener(regla.producto_id) is None
