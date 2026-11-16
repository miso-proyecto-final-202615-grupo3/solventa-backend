import uuid

import httpx
import pytest

from src.infrastructure.gateways.insurancepolicies_service_gateway import (
    InsurancePoliciesGatewayError,
    InsurancePoliciesServiceGateway,
)

COTIZACION_ID = uuid.UUID("95b19edf-6c4b-4437-99db-d84d0ef482fc")
BASE_URL = "http://policies:8000"
PATH = f"/api/v1/insurancepolicies-service/cotizaciones/{COTIZACION_ID}/firma-digital"


async def test_reenvia_operaciones_y_conserva_estado_y_cabeceras():
    calls: list[httpx.Request] = []
    headers = {
        "content-type": "multipart/form-data; boundary=example",
        "idempotency-key": "key-1",
        "x-correlation-id": "corr-1",
        "authorization": "Bearer example",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(201 if request.method == "POST" else 200, json={"firma_id": "1"})

    gateway = InsurancePoliciesServiceGateway(BASE_URL, httpx.MockTransport(handler))
    try:
        assert await gateway.capturar_firma(COTIZACION_ID, b"multipart", headers) == (
            201, {"firma_id": "1"}
        )
        assert await gateway.consultar_firma(COTIZACION_ID, {"x-correlation-id": "corr-1"}) == (
            200, {"firma_id": "1"}
        )
        assert [(call.method, str(call.url)) for call in calls] == [
            ("POST", BASE_URL + PATH), ("GET", BASE_URL + PATH)
        ]
        assert calls[0].content == b"multipart"
        for key, value in headers.items():
            assert calls[0].headers[key] == value
        assert calls[1].headers["x-correlation-id"] == "corr-1"
    finally:
        await gateway.aclose()


@pytest.mark.parametrize("codigo", [404, 409, 413, 415, 422, 503])
async def test_propaga_errores_del_servicio(codigo):
    detalle = {"codigo": "ERROR", "mensaje": "Error de prueba"}
    gateway = InsurancePoliciesServiceGateway(
        BASE_URL, httpx.MockTransport(lambda request: httpx.Response(codigo, json={"detail": detalle}))
    )
    try:
        with pytest.raises(InsurancePoliciesGatewayError) as exc:
            await gateway.capturar_firma(COTIZACION_ID, b"contenido", {})
        assert exc.value.status_code == codigo
        assert exc.value.detail == detalle
    finally:
        await gateway.aclose()


@pytest.mark.parametrize("response", [httpx.Response(200, text="invalido"), httpx.Response(200, json=[])])
async def test_respuesta_exitosa_invalida_es_502(response):
    gateway = InsurancePoliciesServiceGateway(
        BASE_URL, httpx.MockTransport(lambda request: response)
    )
    try:
        with pytest.raises(InsurancePoliciesGatewayError) as exc:
            await gateway.consultar_firma(COTIZACION_ID, {})
        assert exc.value.status_code == 502
    finally:
        await gateway.aclose()


async def test_error_no_json_conserva_status_y_no_expone_contenido():
    gateway = InsurancePoliciesServiceGateway(
        BASE_URL, httpx.MockTransport(lambda request: httpx.Response(503, text="detalle interno"))
    )
    try:
        with pytest.raises(InsurancePoliciesGatewayError) as exc:
            await gateway.consultar_firma(COTIZACION_ID, {})
        assert exc.value.status_code == 503
        assert exc.value.detail == "El servicio de pólizas devolvió un error."
    finally:
        await gateway.aclose()


async def test_sin_conexion_devuelve_503():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("No disponible", request=request)

    gateway = InsurancePoliciesServiceGateway(BASE_URL, httpx.MockTransport(handler))
    try:
        with pytest.raises(InsurancePoliciesGatewayError) as exc:
            await gateway.consultar_firma(COTIZACION_ID, {})
        assert exc.value.status_code == 503
    finally:
        await gateway.aclose()
