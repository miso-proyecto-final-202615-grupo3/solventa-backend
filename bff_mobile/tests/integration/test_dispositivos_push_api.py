"""HU4.2.2 · Registro y borrado del token push en el BFF Móvil: cliente del token, validación y errores."""
import json
import logging
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from src.infrastructure.gateways.identity_service_gateway import IdentityGatewayError, IdentityServiceGateway
from src.main import app
from src.presentation.dependencies import get_cliente_id, get_identity_service_gateway

BASE = "/api/v1/bff-mobile/dispositivos/push"
CLIENTE_ID = "11111111-1111-4111-8111-111111111111"
CONTRACTS = Path(__file__).resolve().parents[3] / "docs" / "contracts" / "notificaciones"


def _muestra(nombre: str) -> dict:
    return json.loads((CONTRACTS / nombre).read_text(encoding="utf-8"))


class IdentityFake:
    def __init__(self) -> None:
        self.llamadas: list[tuple] = []
        self.error: IdentityGatewayError | None = None

    async def registrar_token_push(self, cliente_id, installation_id, token, plataforma, correlation_id):
        self.llamadas.append(("registrar", cliente_id, installation_id, token, plataforma))
        if self.error:
            raise self.error

    async def eliminar_token_push(self, cliente_id, installation_id, correlation_id):
        self.llamadas.append(("eliminar", cliente_id, installation_id))
        if self.error:
            raise self.error


@pytest.fixture
async def client():
    identity = IdentityFake()
    app.dependency_overrides[get_identity_service_gateway] = lambda: identity
    app.dependency_overrides[get_cliente_id] = lambda: CLIENTE_ID
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http, identity
    app.dependency_overrides.clear()


async def test_registra_con_el_cliente_del_token_sin_registrar_el_token(client, caplog):
    http, identity = client
    caplog.set_level(logging.DEBUG)
    body = _muestra("registro-push-request.json")

    response = await http.put(BASE, json=body)

    assert response.status_code == 204
    assert identity.llamadas == [("registrar", CLIENTE_ID, body["installation_id"], body["token"], "ANDROID")]
    assert body["token"] not in caplog.text


async def test_dispositivo_no_vinculado(client):
    http, identity = client
    identity.error = IdentityGatewayError(404, _muestra("error-dispositivo-no-vinculado.json"))

    response = await http.put(BASE, json=_muestra("registro-push-request.json"))

    assert (response.status_code, response.json()["codigo"]) == (404, "DISPOSITIVO_NO_VINCULADO")


async def test_identidad_caida(client):
    http, identity = client
    identity.error = IdentityGatewayError(503, "caído")

    response = await http.put(BASE, json=_muestra("registro-push-request.json"))

    assert (response.status_code, response.json()["codigo"]) == (503, "SERVICIO_NO_DISPONIBLE")


@pytest.mark.parametrize(
    "cambios",
    [{"plataforma": "IOS"}, {"token": ""}, {"token": "x" * 1025}, {"installation_id": "no-es-uuid"}, {"cliente_id": "otro"}],
)
async def test_validacion(client, cambios):
    http, identity = client

    response = await http.put(BASE, json={**_muestra("registro-push-request.json"), **cambios})

    assert response.status_code == 422
    assert identity.llamadas == []


async def test_borrar_al_cerrar_sesion(client):
    http, identity = client
    installation_id = _muestra("registro-push-request.json")["installation_id"]

    response = await http.delete(BASE, params={"installation_id": installation_id})

    assert response.status_code == 204
    assert identity.llamadas == [("eliminar", CLIENTE_ID, installation_id)]


async def test_gateway_reenvia_a_identidad_con_el_token_en_el_cuerpo():
    recibido = []

    def handler(request: httpx.Request) -> httpx.Response:
        recibido.append((request.method, request.url.path, request.content))
        return httpx.Response(204)

    gateway = IdentityServiceGateway("http://identity", transport=httpx.MockTransport(handler))

    await gateway.registrar_token_push(CLIENTE_ID, "inst-1", "tok-123", "ANDROID", "corr")
    await gateway.eliminar_token_push(CLIENTE_ID, "inst-1", "corr")

    assert recibido[0][:2] == ("PUT", f"/api/v1/identity-service/clientes/{CLIENTE_ID}/dispositivos/inst-1/push")
    assert json.loads(recibido[0][2]) == {"token": "tok-123", "plataforma": "ANDROID"}
    assert "tok-123" not in recibido[0][1]
    assert recibido[1][:2] == ("DELETE", f"/api/v1/identity-service/clientes/{CLIENTE_ID}/dispositivos/inst-1/push")
