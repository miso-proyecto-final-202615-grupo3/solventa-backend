from uuid import UUID

from src.core.config import settings
from src.infrastructure.gateways.payments_service_gateway import PaymentsServiceGateway

COTIZACION = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
PAGO = UUID("22222222-2222-4222-8222-222222222222")
PREFIX = "/api/v1/payments-service"


async def test_gateway_pagos_reenvia_operaciones(gateway_client, monkeypatch):
    client, requests = gateway_client
    monkeypatch.setattr(settings, "PAYMENTS_SERVICE_URL", "http://payments-test")
    gateway = PaymentsServiceGateway(client)

    assert (await gateway.resumen_pago(COTIZACION, {"x-correlation-id": "corr"})).status_code == 202
    await gateway.crear_pago(b'{"monto":100}', {"idempotency-key": "pago-1"})
    await gateway.obtener_pago(PAGO, {})

    assert [(r.method, str(r.url)) for r in requests] == [
        ("GET", f"http://payments-test{PREFIX}/cotizaciones/{COTIZACION}/resumen-pago"),
        ("POST", f"http://payments-test{PREFIX}/pagos"),
        ("GET", f"http://payments-test{PREFIX}/pagos/{PAGO}"),
    ]
    assert requests[0].headers["x-correlation-id"] == "corr"
    assert requests[1].content == b'{"monto":100}'
    assert requests[1].headers["idempotency-key"] == "pago-1"
