import json
from uuid import UUID

from src.core.config import settings
from src.infrastructure.gateways.identity_service_gateway import IdentityServiceGateway

SOCIO = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
CLIENTE = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
PREFIX = "/api/v1/identity-service"


async def test_gateway_identity_reenvia_operaciones(gateway_client, monkeypatch):
    client, requests = gateway_client
    monkeypatch.setattr(settings, "IDENTITY_SERVICE_URL", "http://identity-test")
    gateway = IdentityServiceGateway(client)

    assert (await gateway.validar_api_key("clave")).status_code == 202
    await gateway.validar_asociacion(SOCIO, CLIENTE)
    await gateway.registrar_prospecto(SOCIO, b'{"documento":"123"}', {"content-type": "application/json"})
    await gateway.cliente("PUT", CLIENTE, "/consentimiento", b'{"estado":"SI"}', {"x-correlation-id": "corr"})

    assert [(r.method, str(r.url)) for r in requests] == [
        ("POST", f"http://identity-test{PREFIX}/socios/validar-api-key"),
        ("GET", f"http://identity-test{PREFIX}/socios/{SOCIO}/clientes/{CLIENTE}/autorizacion"),
        ("POST", f"http://identity-test{PREFIX}/socios/{SOCIO}/prospectos"),
        ("PUT", f"http://identity-test{PREFIX}/clientes/{CLIENTE}/consentimiento"),
    ]
    assert json.loads(requests[0].content) == {"api_key": "clave"}
    assert requests[2].content == b'{"documento":"123"}'
    assert requests[2].headers["content-type"] == "application/json"
    assert requests[3].content == b'{"estado":"SI"}'
    assert requests[3].headers["x-correlation-id"] == "corr"
