import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.infrastructure.persistence.seed import sembrar_catalogo
from tests.fakes import FakeRedis

BASE = f"{settings.API_PREFIX}/productos"


@pytest.fixture(autouse=True)
async def catalogo(db_session: AsyncSession):
    await sembrar_catalogo(db_session)


async def test_lista_ramos_con_condiciones_y_parametros(api_client: AsyncClient):
    response = await api_client.get(BASE)

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 6
    hipotecario = next(p for p in data if p["codigo"] == "VIDA_HIPOTECARIO")
    assert hipotecario["moneda"] == "COP"
    assert "Open Finance" in hipotecario["mensaje_legal"]
    assert "Open Data" in hipotecario["mensaje_legal"]
    assert hipotecario["fuentes_datos"] == ["OPEN_FINANCE", "OPEN_DATA"]
    assert [p["nombre"] for p in hipotecario["parametros"]] == ["valor_vivienda"]
    assert len(hipotecario["coberturas"]) == 2


async def test_obtiene_ramo_por_codigo(api_client: AsyncClient):
    response = await api_client.get(f"{BASE}/SEGURO_VIAJE")

    assert response.status_code == 200
    assert response.json()["nombre"] == "Seguro de viaje"


async def test_ramo_inexistente(api_client: AsyncClient):
    assert (await api_client.get(f"{BASE}/NO_EXISTE")).status_code == 404


async def test_reglas_se_sirven_desde_cache(
    api_client: AsyncClient, fake_redis: FakeRedis
):
    await api_client.get(BASE)

    assert len(fake_redis.data) == 6
    # segunda lectura funciona aun sin reglas en BD gracias a la caché
    assert (await api_client.get(f"{BASE}/VIDA_HIPOTECARIO")).status_code == 200


async def test_catalogo_funciona_con_redis_caido(
    api_client: AsyncClient, fake_redis: FakeRedis
):
    fake_redis.fallar = True

    response = await api_client.get(BASE)

    assert response.status_code == 200
    assert len(response.json()) == 6
