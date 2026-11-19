from uuid import UUID

from src.core.config import settings
from src.infrastructure.gateways.insurancepolicies_service_gateway import InsurancePoliciesServiceGateway

COTIZACION = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
PREFIX = "/api/v1/insurancepolicies-service"


async def test_gateway_polizas_reenvia_operaciones(gateway_client, monkeypatch):
    client, requests = gateway_client
    monkeypatch.setattr(settings, "INSURANCEPOLICIES_SERVICE_URL", "http://policies-test")
    gateway = InsurancePoliciesServiceGateway(client)

    assert (await gateway.cotizacion("POST", COTIZACION, "/firma-digital", b"firma", {"content-type": "multipart/form-data; boundary=x"})).status_code == 202
    await gateway.polizas("/mis-polizas", {"x-client-id": "cliente"})

    assert [(r.method, str(r.url)) for r in requests] == [
        ("POST", f"http://policies-test{PREFIX}/cotizaciones/{COTIZACION}/firma-digital"),
        ("GET", f"http://policies-test{PREFIX}/polizas/mis-polizas"),
    ]
    assert requests[0].content == b"firma"
    assert requests[0].headers["content-type"] == "multipart/form-data; boundary=x"
    assert requests[1].headers["x-client-id"] == "cliente"
