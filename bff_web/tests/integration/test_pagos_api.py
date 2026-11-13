import json
from uuid import UUID

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from src.infrastructure.gateways.payments_service_gateway import PaymentsServiceGateway
from src.main import app
from src.presentation.dependencies import get_payments_service_gateway

COTIZACION_ID = UUID("95b19edf-6c4b-4437-99db-d84d0ef482fc")
PAGO_ID = UUID("0f5d2a4e-3a54-4b0e-9a3b-8d6e2f1c7a10")
BASE = "/api/v1/bff-web"
UPSTREAM = "/api/v1/payments-service"


@pytest.fixture
def upstream():
    class Upstream:
        def __init__(self):
            self.calls: list[httpx.Request] = []
            self.status_code = 200
            self.body = {"pago_id": str(PAGO_ID), "estado": "APROBADO"}

        def handle(self, request: httpx.Request) -> httpx.Response:
            self.calls.append(request)
            return httpx.Response(self.status_code, json=self.body)

    return Upstream()


@pytest.fixture
async def client(upstream):
    async def get_gateway():
        gateway = PaymentsServiceGateway(
            base_url="http://payments", transport=httpx.MockTransport(upstream.handle)
        )
        try:
            yield gateway
        finally:
            await gateway.aclose()

    app.dependency_overrides[get_payments_service_gateway] = get_gateway
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_payments_service_gateway, None)


@pytest.mark.parametrize(
    ("path", "destino"),
    [
        (
            f"/cotizaciones/{COTIZACION_ID}/resumen-pago",
            f"/cotizaciones/{COTIZACION_ID}/resumen-pago",
        ),
        (f"/pagos/{PAGO_ID}", f"/pagos/{PAGO_ID}"),
    ],
)
async def test_consultas_reenvian_ruta_y_cabeceras(client, upstream, path, destino):
    response = await client.get(
        BASE + path,
        headers={"X-Correlation-Id": "corr-1", "Authorization": "Bearer example"},
    )

    assert response.status_code == 200
    assert response.json() == upstream.body
    request = upstream.calls[0]
    assert request.method == "GET"
    assert request.url.path == UPSTREAM + destino
    assert request.headers["x-correlation-id"] == "corr-1"
    assert request.headers["authorization"] == "Bearer example"


@pytest.mark.parametrize("status_code", [200, 201])
@pytest.mark.parametrize(
    "payload",
    [
        {"cotizacion_id": str(COTIZACION_ID), "cliente_id": str(PAGO_ID), "paypal_email": "a@example.com"},
        {
            "cotizacion_id": str(COTIZACION_ID),
            "cliente_id": str(PAGO_ID),
            "metodo_pago": "TARJETA_CREDITO",
            "numero_tarjeta": "4242424242424242",
            "mes_expiracion": 12,
            "anio_expiracion": 2099,
            "cvv": "123",
        },
    ],
)
async def test_procesa_pago_conservando_cuerpo_cabeceras_y_status(client, upstream, status_code, payload):
    upstream.status_code = status_code
    response = await client.post(
        BASE + "/pagos",
        json=payload,
        headers={
            "Idempotency-Key": "key-1",
            "X-Correlation-Id": "corr-1",
            "Authorization": "Bearer example",
            "X-Unrelated": "not-forwarded",
        },
    )

    assert response.status_code == status_code
    assert response.json() == upstream.body
    request = upstream.calls[0]
    assert request.method == "POST"
    assert request.url.path == UPSTREAM + "/pagos"
    assert json.loads(request.content) == payload
    assert request.headers["content-type"] == "application/json"
    assert request.headers["idempotency-key"] == "key-1"
    assert request.headers["x-correlation-id"] == "corr-1"
    assert request.headers["authorization"] == "Bearer example"
    assert "x-unrelated" not in request.headers


@pytest.mark.parametrize("status_code", [404, 409, 422, 503])
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", f"/cotizaciones/{COTIZACION_ID}/resumen-pago"),
        ("POST", "/pagos"),
        ("GET", f"/pagos/{PAGO_ID}"),
    ],
)
async def test_propaga_errores_del_servicio(client, upstream, status_code, method, path):
    upstream.status_code = status_code
    upstream.body = {"detail": {"codigo": "ERROR", "mensaje": "No se pudo procesar"}}
    response = await client.request(method, BASE + path)
    assert response.status_code == status_code
    assert response.json() == upstream.body


async def test_reenvia_error_de_validacion_sin_clave_de_idempotencia(client, upstream):
    upstream.status_code = 422
    upstream.body = {"detail": [{"loc": ["body", "cliente_id"], "msg": "Field required"}]}
    response = await client.post(BASE + "/pagos", json={})
    assert response.status_code == 422
    assert response.json() == upstream.body
    assert "idempotency-key" not in upstream.calls[0].headers


@pytest.mark.parametrize("path", ["/pagos/invalido", "/cotizaciones/invalida/resumen-pago"])
async def test_uuid_invalido_no_se_reenvia(client, upstream, path):
    response = await client.get(BASE + path)
    assert response.status_code == 422
    assert upstream.calls == []


async def test_openapi_documenta_el_pago_y_reintento_idempotente(client):
    schema = (await client.get("/openapi.json")).json()
    operation = schema["paths"]["/api/v1/bff-web/pagos"]["post"]
    body = operation["requestBody"]["content"]["application/json"]["schema"]
    assert set(body["required"]) == {"cliente_id", "cotizacion_id"}
    assert set(body["properties"]["metodo_pago"]["enum"]) == {"PAYPAL", "TARJETA_CREDITO"}
    assert {"paypal_email", "numero_tarjeta", "mes_expiracion", "anio_expiracion", "cvv"} <= set(body["properties"])
    assert "tarjeta_token" not in body["properties"]
    assert any(p["name"] == "Idempotency-Key" and p["required"] for p in operation["parameters"])
    assert "200" in operation["responses"] and "201" in operation["responses"]
