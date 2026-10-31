import httpx
import pytest

from src.infrastructure.gateways.quotingengine_service_gateway import (
    QuotingEngineGatewayError,
    QuotingEngineServiceGateway,
)

BASE = "http://quotingengine-host:8000"
PRODUCTOS_PATH = "/api/v1/quotingengine-service/productos"
PRODUCTO_PATH = f"{PRODUCTOS_PATH}/auto"
COTIZACIONES_PATH = "/api/v1/quotingengine-service/cotizaciones"
COTIZACION_ID = "95b19edf-6c4b-4437-99db-d84d0ef482fc"
PAYLOAD = b'{"cliente_id":"cliente-1","producto_codigo":"auto","parametros":{}}'


async def test_reenvia_operaciones_al_servicio_de_cotizacion():
    calls: list[httpx.Request] = []
    responses = [
        httpx.Response(200, json=[{"codigo": "auto"}]),
        httpx.Response(200, json={"codigo": "auto"}),
        httpx.Response(201, json={"cotizacion_id": COTIZACION_ID}),
        httpx.Response(200, json={"cotizacion_id": COTIZACION_ID}),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return responses[len(calls) - 1]

    gateway = QuotingEngineServiceGateway(
        base_url=BASE, transport=httpx.MockTransport(handler)
    )
    try:
        assert await gateway.listar_productos() == [{"codigo": "auto"}]
        assert await gateway.obtener_producto("auto") == {"codigo": "auto"}
        assert await gateway.solicitar_cotizacion(
            PAYLOAD, "application/vnd.api+json"
        ) == {"cotizacion_id": COTIZACION_ID}
        assert await gateway.obtener_cotizacion(COTIZACION_ID) == {
            "cotizacion_id": COTIZACION_ID
        }

        assert [(call.method, str(call.url)) for call in calls] == [
            ("GET", f"{BASE}{PRODUCTOS_PATH}"),
            ("GET", f"{BASE}{PRODUCTO_PATH}"),
            ("POST", f"{BASE}{COTIZACIONES_PATH}"),
            ("GET", f"{BASE}{COTIZACIONES_PATH}/{COTIZACION_ID}"),
        ]
        assert calls[2].content == PAYLOAD
        assert calls[2].headers["content-type"] == "application/vnd.api+json"
    finally:
        await gateway.aclose()


async def test_propaga_error_del_servicio_de_cotizacion():
    gateway = QuotingEngineServiceGateway(
        base_url=BASE,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                404, json={"detail": "Ramo de seguro no encontrado."}
            )
        ),
    )
    try:
        with pytest.raises(QuotingEngineGatewayError) as exc:
            await gateway.obtener_producto("inexistente")
        assert exc.value.status_code == 404
        assert exc.value.detail == "Ramo de seguro no encontrado."
    finally:
        await gateway.aclose()


async def test_error_de_red_se_mapea_como_503():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin conexión")

    gateway = QuotingEngineServiceGateway(
        base_url=BASE, transport=httpx.MockTransport(handler)
    )
    try:
        with pytest.raises(QuotingEngineGatewayError) as exc:
            await gateway.listar_productos()
        assert exc.value.status_code == 503
    finally:
        await gateway.aclose()
