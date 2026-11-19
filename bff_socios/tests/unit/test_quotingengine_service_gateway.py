import json
from uuid import UUID

from src.core.config import settings
from src.infrastructure.gateways.quotingengine_service_gateway import QuotingEngineServiceGateway

COTIZACION = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
PREFIX = "/api/v1/quotingengine-service"


async def test_gateway_cotizacion_reenvia_operaciones(gateway_client, monkeypatch):
    client, requests = gateway_client
    monkeypatch.setattr(settings, "QUOTINGENGINE_SERVICE_URL", "http://quoting-test")
    gateway = QuotingEngineServiceGateway(client)

    assert (await gateway.productos("", {"x-correlation-id": "corr"})).status_code == 202
    await gateway.productos("VIDA", {})
    await gateway.crear_cotizacion({"producto": "VIDA"}, {"idempotency-key": "k"})
    await gateway.obtener_cotizacion(COTIZACION)
    await gateway.cotizacion("POST", COTIZACION, "/condiciones/decisiones", b'{"decision":"SI"}', {"content-type": "application/json"})

    assert [(r.method, str(r.url)) for r in requests] == [
        ("GET", f"http://quoting-test{PREFIX}/productos"),
        ("GET", f"http://quoting-test{PREFIX}/productos/VIDA"),
        ("POST", f"http://quoting-test{PREFIX}/cotizaciones"),
        ("GET", f"http://quoting-test{PREFIX}/cotizaciones/{COTIZACION}"),
        ("POST", f"http://quoting-test{PREFIX}/cotizaciones/{COTIZACION}/condiciones/decisiones"),
    ]
    assert requests[0].headers["x-correlation-id"] == "corr"
    assert json.loads(requests[2].content) == {"producto": "VIDA"}
    assert requests[2].headers["idempotency-key"] == "k"
    assert requests[4].content == b'{"decision":"SI"}'
    assert requests[4].headers["content-type"] == "application/json"
