import httpx
import pytest

from src.infrastructure.gateways.identity_service_gateway import (
    IdentityGatewayError,
    IdentityServiceGateway,
)

BASE = "http://identity-host:8000"
PATH = "/api/v1/identity-service/consentimientos"


async def test_consulta_la_auditoria_con_los_parametros():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"cliente": {}, "eventos": []})

    gateway = IdentityServiceGateway(
        base_url=BASE, transport=httpx.MockTransport(handler)
    )
    try:
        resultado = await gateway.consultar_auditoria_consentimiento(
            {"correo": "ana@example.com"}
        )
    finally:
        await gateway.aclose()

    assert resultado == {"cliente": {}, "eventos": []}
    assert calls[0].method == "GET"
    assert calls[0].url.path == PATH
    assert calls[0].url.params["correo"] == "ana@example.com"


async def test_propaga_el_error_de_identity():
    gateway = IdentityServiceGateway(
        base_url=BASE,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(404, json={"detail": "No hay un cliente con ese dato."})
        ),
    )
    try:
        with pytest.raises(IdentityGatewayError) as error:
            await gateway.consultar_auditoria_consentimiento({"correo": "x@example.com"})
    finally:
        await gateway.aclose()

    assert error.value.status_code == 404
