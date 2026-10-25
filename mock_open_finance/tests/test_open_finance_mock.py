import uuid

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


async def test_retorna_senales_financieras_mock(client):
    response = await client.post("/profile", json={"cliente_id": str(uuid.uuid4())})

    assert response.status_code == 200
    assert response.json() == {
        "ingreso_mensual": "8500000",
        "ahorros_liquidos": "25500000",
        "dti_pct": "28",
        "sobregiros_12_meses": 0,
        "score": 820,
    }


async def test_simula_caida_de_open_finance(client, monkeypatch):
    monkeypatch.setenv("MOCK_OPEN_FINANCE_STATUS", "UNAVAILABLE")

    response = await client.post("/profile", json={"cliente_id": str(uuid.uuid4())})

    assert response.status_code == 503
