import httpx
import pytest
from decimal import Decimal

from src.application.ports.open_data_gateway import OpenDataNoDisponibleError
from src.domain.open_data import CategoriaOpenData
from src.infrastructure.cache.open_data_redis_cache import OpenDataRedisCache
from src.infrastructure.gateways.open_data_http_client import OpenDataHttpClient
from tests.fakes import FakeRedis


async def test_consulta_perfil_territorial():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "categoria": "BAJO_RIESGO",
                    "id_territorial": 0.95,
                    "ir_publico": 1.0,
                },
            )
        )
    ) as client:
        perfil = await OpenDataHttpClient(
            client, "http://opendata"
        ).obtener_riesgo({"municipio": "Bogota", "zona": "URBANA", "estrato": 4})

    assert perfil.categoria == CategoriaOpenData.BAJO_RIESGO
    assert perfil.categoria.factor == Decimal("0.95")


async def test_respuesta_no_disponible_se_normaliza():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(503))
    ) as client:
        with pytest.raises(OpenDataNoDisponibleError):
            await OpenDataHttpClient(client, "http://opendata").obtener_riesgo({})


async def test_cache_territorial_seguida_por_ubicacion_y_ttl():
    redis = FakeRedis()
    cache = OpenDataRedisCache(redis, ttl_seconds=50)
    ubicacion = {"municipio": "Bogota", "zona": "URBANA", "estrato": 4}
    from src.domain.open_data import PerfilTerritorial

    await cache.guardar(ubicacion, PerfilTerritorial(CategoriaOpenData.BAJO_RIESGO))

    assert await cache.obtener(ubicacion) == CategoriaOpenData.BAJO_RIESGO
    assert next(iter(redis.ttls.values())) == 50
