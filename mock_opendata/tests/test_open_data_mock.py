import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client


async def test_bogota_urbana_estrato_cuatro_corresponde_a_riesgo_bajo(client):
    response = await client.post(
        "/risk",
        json={"municipio": "Bogotá D.C.", "zona": "URBANA", "estrato": 4},
    )

    assert response.status_code == 200
    assert response.json() == {
        "categoria": "BAJO_RIESGO",
        "id_territorial": 0.95,
        "ir_publico": 1.0,
    }


async def test_rechaza_ubicacion_invalida(client):
    response = await client.post(
        "/risk",
        json={"municipio": "Bogotá", "zona": "URBANA", "estrato": 7},
    )

    assert response.status_code == 422


async def test_simula_indisponibilidad_del_proveedor(client, monkeypatch):
    monkeypatch.setenv("MOCK_OPENDATA_STATUS", "UNAVAILABLE")

    response = await client.post(
        "/risk",
        json={"municipio": "Bogotá", "zona": "URBANA", "estrato": 4},
    )

    assert response.status_code == 503
