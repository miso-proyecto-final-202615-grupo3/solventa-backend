from decimal import Decimal

from src.domain.open_data import CategoriaOpenData, PerfilTerritorial
from src.infrastructure.cache.open_data_redis_cache import OpenDataRedisCache


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.ttls = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ex):
        self.values[key] = value
        self.ttls[key] = ex

    async def delete(self, key):
        self.values.pop(key, None)


async def test_cache_guarda_y_recupera_categoria_por_ubicacion():
    redis = FakeRedis()
    cache = OpenDataRedisCache(redis, ttl_seconds=301)
    location = {"municipio": "Bogota", "zona": "URBANA", "estrato": 4}
    profile = PerfilTerritorial(
        categoria=CategoriaOpenData.BAJO_RIESGO,
        id_territorial=Decimal("0.95"),
        ir_publico=Decimal("1.00"),
    )

    await cache.guardar(location, profile)

    assert cache.ttl_seconds == 301
    assert await cache.obtener(location) == CategoriaOpenData.BAJO_RIESGO
    assert len(redis.ttls) == 1


async def test_cache_invalida_entrada_corrupta():
    redis = FakeRedis()
    cache = OpenDataRedisCache(redis)
    location = {"municipio": "Bogota", "zona": "URBANA", "estrato": 4}
    redis.values[cache._key(location)] = '{"categoria":"OTRA"}'

    assert await cache.obtener(location) is None
    assert cache._key(location) not in redis.values
