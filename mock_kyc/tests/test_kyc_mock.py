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


async def test_verificacion_retorna_estado_predeterminado_e_identificador(client, monkeypatch):
    monkeypatch.delenv("MOCK_KYC_STATUS", raising=False)
    payload = {"document_type": "CC", "document_number": "123456789"}

    response = await client.post("/verify", json=payload)
    second_response = await client.post("/verify", json=payload)

    assert response.status_code == 200
    assert second_response.status_code == 200
    result = response.json()
    assert set(result) == {"verification_id", "status"}
    assert result["status"] == "PASSED"
    assert uuid.UUID(result["verification_id"]).version == 4
    assert uuid.UUID(second_response.json()["verification_id"]).version == 4
    assert result["verification_id"] != second_response.json()["verification_id"]


@pytest.mark.parametrize(
    ("configured_status", "expected_status"),
    [
        ("PASSED", "PASSED"),
        ("failed", "FAILED"),
        ("PENDING", "PENDING"),
        ("INVALID", "PASSED"),
        ("", "PASSED"),
    ],
)
async def test_verificacion_usa_estado_configurado(
    client, monkeypatch, configured_status, expected_status
):
    monkeypatch.setenv("MOCK_KYC_STATUS", configured_status)

    response = await client.post(
        "/verify", json={"document_type": "CC", "document_number": "123456789"}
    )

    assert response.status_code == 200
    assert response.json()["status"] == expected_status


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"document_type": "", "document_number": "123456789"},
        {"document_type": "CC", "document_number": ""},
        {"document_type": "CC"},
        {"document_number": "123456789"},
    ],
)
async def test_rechaza_documentos_invalidos(client, payload):
    response = await client.post("/verify", json=payload)

    assert response.status_code == 422
