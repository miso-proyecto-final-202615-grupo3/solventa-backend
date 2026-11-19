from uuid import UUID

import httpx
import pytest

from src.core.config import settings
from src.main import app
from src.presentation.dependencies import get_http_client

SOCIO = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
CLIENTE = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
OTRO = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
COTIZACION = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
VERIFICACION = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
POLIZA = UUID("11111111-1111-4111-8111-111111111111")
PAGO = UUID("22222222-2222-4222-8222-222222222222")

BASE = "/api/v1/bff-socios"
IDENTITY = "/api/v1/identity-service"
QUOTING = "/api/v1/quotingengine-service"
POLICIES = "/api/v1/insurancepolicies-service"
PAYMENTS = "/api/v1/payments-service"


class Backend:
    def __init__(self):
        self.llamadas: list[httpx.Request] = []
        self.respuestas: dict[tuple[str, str], httpx.Response] = {}
        self.cotizacion = {"cotizacion_id": str(COTIZACION), "cliente_id": str(CLIENTE)}

    def responder(self, metodo: str, ruta: str, response: httpx.Response) -> None:
        self.respuestas[(metodo, ruta)] = response

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.llamadas.append(request)
        assert "x-api-key" not in request.headers
        assert "authorization" not in request.headers
        path = request.url.path
        response = self.respuestas.get((request.method, path))
        if response is not None:
            return response
        if path == f"{IDENTITY}/socios/validar-api-key":
            return httpx.Response(200, json={"socio_id": str(SOCIO)})
        if path == f"{IDENTITY}/socios/{SOCIO}/clientes/{CLIENTE}/autorizacion":
            return httpx.Response(204)
        if path == f"{QUOTING}/cotizaciones/{COTIZACION}" and request.method == "GET":
            return httpx.Response(200, json=self.cotizacion)
        raise AssertionError(f"Solicitud inesperada: {request.method} {path}")


@pytest.fixture
async def bff(monkeypatch):
    for atributo, url in (
        ("IDENTITY_SERVICE_URL", "http://identity"),
        ("QUOTINGENGINE_SERVICE_URL", "http://quoting"),
        ("INSURANCEPOLICIES_SERVICE_URL", "http://policies"),
        ("PAYMENTS_SERVICE_URL", "http://payments"),
    ):
        monkeypatch.setattr(settings, atributo, url)
    backend = Backend()
    async with httpx.AsyncClient(transport=httpx.MockTransport(backend.handle)) as upstream:
        app.dependency_overrides[get_http_client] = lambda: upstream
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://bff"
            ) as client:
                yield client, backend
        finally:
            app.dependency_overrides.pop(get_http_client, None)


@pytest.fixture
def headers_cliente():
    return {
        "X-API-Key": "clave-socio",
        "X-Client-Id": str(CLIENTE),
        "X-Correlation-Id": "corr-1",
        "Idempotency-Key": "idempotencia-1",
        "Authorization": "Bearer no-reenviar",
    }


@pytest.fixture
async def gateway_client():
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(202, json={"resultado": "ok"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        yield client, requests
