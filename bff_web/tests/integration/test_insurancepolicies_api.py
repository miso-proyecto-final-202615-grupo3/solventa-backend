from email import policy
from email.parser import BytesParser
from uuid import UUID

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from src.core.config import settings
from src.infrastructure.gateways.insurancepolicies_service_gateway import (
    InsurancePoliciesServiceGateway,
)
from src.main import app
from src.presentation.dependencies import get_insurancepolicies_service_gateway

COTIZACION_ID = UUID("95b19edf-6c4b-4437-99db-d84d0ef482fc")
URL = f"/api/v1/bff-web/cotizaciones/{COTIZACION_ID}/firma-digital"
UPSTREAM_PATH = f"/api/v1/insurancepolicies-service/cotizaciones/{COTIZACION_ID}/firma-digital"
PNG = b"\x89PNG\r\n\x1a\ncontenido-de-firma"


@pytest.fixture
def upstream():
    class Upstream:
        calls: list[httpx.Request]

        def __init__(self):
            self.calls = []
            self.status_code = 201
            self.body = {"firma_id": "firma-1", "estado": "CAPTURADA"}

        def handle(self, request: httpx.Request) -> httpx.Response:
            self.calls.append(request)
            return httpx.Response(self.status_code, json=self.body)

    return Upstream()


@pytest.fixture
async def client(upstream):
    async def get_gateway():
        gateway = InsurancePoliciesServiceGateway(
            base_url="http://insurancepolicies", transport=httpx.MockTransport(upstream.handle)
        )
        try:
            yield gateway
        finally:
            await gateway.aclose()

    app.dependency_overrides[get_insurancepolicies_service_gateway] = get_gateway
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_insurancepolicies_service_gateway, None)


def _multipart(request: httpx.Request) -> dict[str, bytes]:
    content_type = request.headers["content-type"]
    message = BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode()
        + request.content
    )
    return {
        part.get_param("name", header="content-disposition"): part.get_payload(decode=True)
        for part in message.iter_parts()
    }


@pytest.mark.parametrize("status_code", [201, 200])
async def test_captura_reenvia_multipart_y_estado(client, upstream, status_code):
    upstream.status_code = status_code
    response = await client.post(
        URL,
        data={"cliente_id": "cliente", "producto_id": "producto"},
        files={"firma": ("firma.png", PNG, "image/png")},
        headers={
            "Idempotency-Key": "key-1",
            "X-Correlation-Id": "corr-1",
            "Authorization": "Bearer example",
            "X-Unrelated": "not-forwarded",
        },
    )
    assert response.status_code == status_code
    assert response.json() == upstream.body
    assert len(upstream.calls) == 1
    request = upstream.calls[0]
    assert request.method == "POST"
    assert request.url.path == UPSTREAM_PATH
    assert _multipart(request) == {
        "cliente_id": b"cliente", "producto_id": b"producto", "firma": PNG
    }
    assert request.headers["idempotency-key"] == "key-1"
    assert request.headers["x-correlation-id"] == "corr-1"
    assert request.headers["authorization"] == "Bearer example"
    assert "x-unrelated" not in request.headers


async def test_consulta_firma(client, upstream):
    upstream.status_code = 200
    response = await client.get(URL, headers={"X-Correlation-Id": "corr-2"})
    assert response.status_code == 200
    assert response.json() == upstream.body
    assert upstream.calls[0].method == "GET"
    assert upstream.calls[0].url.path == UPSTREAM_PATH
    assert upstream.calls[0].headers["x-correlation-id"] == "corr-2"


@pytest.mark.parametrize("status_code", [404, 409, 413, 415, 422, 503])
@pytest.mark.parametrize("method", ["GET", "POST"])
async def test_propaga_errores(client, upstream, status_code, method):
    upstream.status_code = status_code
    upstream.body = {"detail": {"codigo": "ERROR", "mensaje": "No se pudo procesar"}}
    response = await client.request(method, URL)
    assert response.status_code == status_code
    assert response.json() == upstream.body


async def test_uuid_invalido_no_se_reenvia(client, upstream):
    response = await client.get("/api/v1/bff-web/cotizaciones/invalida/firma-digital")
    assert response.status_code == 422
    assert upstream.calls == []


async def test_limite_del_cuerpo_en_stream_sin_content_length(client, upstream, monkeypatch):
    monkeypatch.setattr(settings, "FIRMA_MAX_REQUEST_BYTES", 8)

    async def chunks():
        yield b"12345"
        yield b"6789"

    response = await client.post(URL, content=chunks())
    assert response.status_code == 413
    assert response.json()["detail"]["codigo"] == "FIRMA_DEMASIADO_GRANDE"
    assert upstream.calls == []


async def test_cuerpo_exactamente_en_el_limite_se_reenvia(client, upstream, monkeypatch):
    monkeypatch.setattr(settings, "FIRMA_MAX_REQUEST_BYTES", 8)
    response = await client.post(URL, content=b"12345678")
    assert response.status_code == 201
    assert upstream.calls[0].content == b"12345678"


async def test_propaga_errores_de_validacion_en_formato_lista(client, upstream):
    upstream.status_code = 422
    upstream.body = {"detail": [{"loc": ["body", "cliente_id"], "msg": "Field required"}]}
    response = await client.post(URL, content=b"")
    assert response.status_code == 422
    assert response.json() == upstream.body
    assert "idempotency-key" not in upstream.calls[0].headers


async def test_openapi_documenta_formulario_y_clave(client):
    response = await client.get("/openapi.json")
    operation = response.json()["paths"]["/api/v1/bff-web/cotizaciones/{cotizacion_id}/firma-digital"]["post"]
    schema = operation["requestBody"]["content"]["multipart/form-data"]["schema"]
    assert set(schema["required"]) == {"cliente_id", "producto_id", "firma"}
    assert schema["properties"]["firma"]["format"] == "binary"
    assert any(
        p["name"] == "Idempotency-Key" and p["required"] and p["in"] == "header"
        for p in operation["parameters"]
    )
    assert "200" in operation["responses"] and "201" in operation["responses"]
