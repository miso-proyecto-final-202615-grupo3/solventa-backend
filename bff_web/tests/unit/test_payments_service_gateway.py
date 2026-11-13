from uuid import UUID

import httpx
import pytest

from src.infrastructure.gateways.payments_service_gateway import (
    PaymentsGatewayError,
    PaymentsServiceGateway,
)

COTIZACION_ID = UUID("95b19edf-6c4b-4437-99db-d84d0ef482fc")
PAGO_ID = UUID("0f5d2a4e-3a54-4b0e-9a3b-8d6e2f1c7a10")
PREFIX = "/api/v1/payments-service"


async def test_reenvia_las_tres_operaciones_y_cierra_el_cliente():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(201 if request.method == "POST" else 200, json={"ok": True})

    gateway = PaymentsServiceGateway("http://payments", httpx.MockTransport(handler))
    headers = {"content-type": "application/json", "idempotency-key": "k"}
    try:
        assert await gateway.obtener_resumen_pago(COTIZACION_ID, {}) == (200, {"ok": True})
        assert await gateway.procesar_pago(b'{"x":1}', headers) == (201, {"ok": True})
        assert await gateway.obtener_pago(PAGO_ID, {}) == (200, {"ok": True})
        assert [(r.method, r.url.path) for r in calls] == [
            ("GET", f"{PREFIX}/cotizaciones/{COTIZACION_ID}/resumen-pago"),
            ("POST", f"{PREFIX}/pagos"),
            ("GET", f"{PREFIX}/pagos/{PAGO_ID}"),
        ]
        assert calls[1].content == b'{"x":1}'
        assert calls[1].headers["idempotency-key"] == "k"
    finally:
        await gateway.aclose()
    assert gateway._client.is_closed


@pytest.mark.parametrize("status_code", [404, 409, 422, 503])
async def test_error_del_servicio_conserva_el_detalle(status_code):
    detail = {"codigo": "ERROR", "mensaje": "error"}
    gateway = PaymentsServiceGateway(
        "http://payments",
        httpx.MockTransport(lambda request: httpx.Response(status_code, json={"detail": detail})),
    )
    try:
        with pytest.raises(PaymentsGatewayError) as exc:
            await gateway.procesar_pago(b"{}", {})
        assert (exc.value.status_code, exc.value.detail) == (status_code, detail)
    finally:
        await gateway.aclose()


@pytest.mark.parametrize("response", [httpx.Response(200, text="invalido"), httpx.Response(200, json=[])])
async def test_respuesta_exitosa_invalida_es_502(response):
    gateway = PaymentsServiceGateway("http://payments", httpx.MockTransport(lambda request: response))
    try:
        with pytest.raises(PaymentsGatewayError) as exc:
            await gateway.obtener_pago(PAGO_ID, {})
        assert exc.value.status_code == 502
    finally:
        await gateway.aclose()


async def test_error_no_json_no_expone_contenido_interno():
    gateway = PaymentsServiceGateway(
        "http://payments", httpx.MockTransport(lambda request: httpx.Response(503, text="interno"))
    )
    try:
        with pytest.raises(PaymentsGatewayError) as exc:
            await gateway.obtener_pago(PAGO_ID, {})
        assert (exc.value.status_code, exc.value.detail) == (
            503, "El servicio de pagos devolvió un error."
        )
    finally:
        await gateway.aclose()


@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ReadTimeout])
async def test_error_de_red_indica_reintentar_con_la_misma_clave(error):
    def handler(request: httpx.Request) -> httpx.Response:
        raise error("no disponible", request=request)

    gateway = PaymentsServiceGateway("http://payments", httpx.MockTransport(handler))
    try:
        with pytest.raises(PaymentsGatewayError) as exc:
            await gateway.procesar_pago(b"{}", {"idempotency-key": "k"})
        assert exc.value.status_code == 503
        assert "misma Idempotency-Key" in exc.value.detail
    finally:
        await gateway.aclose()
