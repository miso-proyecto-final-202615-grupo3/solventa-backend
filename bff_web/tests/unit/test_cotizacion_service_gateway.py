import httpx
import pytest

from src.infrastructure.gateways.cotizacion_service_gateway import (
    CotizacionGatewayError,
    CotizacionServiceGateway,
)


PAYLOAD = b'{"cliente_id":"123","ramo":"VIDA_HIPOTECARIO"}'
PATH = "/api/v1/motor-cotizacion/cotizar"


async def test_cotizar_reenvia_json_y_devuelve_respuesta():
    calls = []
    response_body = {"estado": "COTIZADA", "prima_mensual": 48046.25}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=response_body)

    gateway = CotizacionServiceGateway(
        base_url="http://motor-host:8000",
        transport=httpx.MockTransport(handler),
    )
    try:
        response = await gateway.cotizar(PAYLOAD)
    finally:
        await gateway.aclose()

    assert response == response_body
    assert str(calls[0].url) == f"http://motor-host:8000{PATH}"
    assert calls[0].method == "POST"
    assert calls[0].content == PAYLOAD


async def test_cotizar_propaga_error_funcional_del_motor():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"detail": "CONSENTIMIENTO_NO_ACTIVO"})

    gateway = CotizacionServiceGateway(
        base_url="http://motor-host:8000",
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(CotizacionGatewayError) as error:
            await gateway.cotizar(PAYLOAD)
    finally:
        await gateway.aclose()

    assert error.value.status_code == 403
    assert error.value.detail == "CONSENTIMIENTO_NO_ACTIVO"


async def test_cotizar_mapea_motor_inaccesible_a_503():
    async def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no disponible")

    gateway = CotizacionServiceGateway(
        base_url="http://motor-host:8000",
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(CotizacionGatewayError) as error:
            await gateway.cotizar(PAYLOAD)
    finally:
        await gateway.aclose()

    assert error.value.status_code == 503
