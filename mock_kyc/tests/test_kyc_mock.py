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


def _archivos():
    return {
        "documento_frontal": ("frontal.jpg", b"\xff\xd8\xff-frontal", "image/jpeg"),
        "documento_reverso": ("reverso.jpg", b"\xff\xd8\xff-reverso", "image/jpeg"),
    }


async def test_inicio_retorna_identificador_nuevo_y_descarta_documentos(client):
    data = {"cliente_id": str(uuid.uuid4()), "ruta_documento_frontal": "s3://b/k"}

    first = await client.post("/verificaciones-kyc-aml", data=data, files=_archivos())
    second = await client.post("/verificaciones-kyc-aml", data=data, files=_archivos())

    assert first.status_code == 200
    assert set(first.json()) == {"verification_id"}
    assert uuid.UUID(first.json()["verification_id"]).version == 4
    assert first.json()["verification_id"] != second.json()["verification_id"]


async def test_inicio_no_exige_cuerpo(client):
    response = await client.post("/verificaciones-kyc-aml")

    assert response.status_code == 200


async def test_resultado_por_defecto_aprobado(client, monkeypatch):
    monkeypatch.delenv("MOCK_KYC_STATUS", raising=False)
    monkeypatch.delenv("MOCK_AML_STATUS", raising=False)
    verification_id = str(uuid.uuid4())

    response = await client.get(f"/verificaciones-kyc-aml/{verification_id}")

    assert response.status_code == 200
    assert response.json() == {
        "verification_id": verification_id,
        "kyc_status": "PASSED",
        "aml_status": "PASSED",
    }


@pytest.mark.parametrize(
    ("kyc", "aml"),
    [("PASSED", "FAILED"), ("FAILED", "PASSED"), ("PENDING", "PASSED"), ("FAILED", "FAILED")],
)
async def test_resultado_usa_variables_de_entorno_por_separado(client, monkeypatch, kyc, aml):
    monkeypatch.setenv("MOCK_KYC_STATUS", kyc)
    monkeypatch.setenv("MOCK_AML_STATUS", aml)

    response = await client.get(f"/verificaciones-kyc-aml/{uuid.uuid4()}")

    assert response.status_code == 200
    assert response.json()["kyc_status"] == kyc
    assert response.json()["aml_status"] == aml


async def test_ruta_verify_anterior_ya_no_existe(client):
    response = await client.post(
        "/verify", json={"document_type": "CC", "document_number": "123456789"}
    )

    assert response.status_code == 404
