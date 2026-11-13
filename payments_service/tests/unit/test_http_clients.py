import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from src.application.ports.cotizaciones import CotizacionNoEncontradaError
from src.application.ports.proveedor_pago import (
    DatosTarjeta,
    ProveedorPagoError,
    SolicitudCobro,
    SolicitudInvalidaError,
)
from src.application.ports.servicios import ServicioNoDisponibleError
from src.infrastructure.gateways.insurancepolicies_http_client import InsurancePoliciesHttpClient
from src.infrastructure.gateways.payment_provider_http_client import (
    ClienteProveedorPago,
    PayPalProveedor,
    TarjetaCreditoProveedor,
)
from src.infrastructure.gateways.quotingengine_http_client import QuotingEngineHttpClient

COTIZACION_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
CLIENTE_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
BASE = "http://servicio"
CORRELACION = "corr-7"
COTIZACION_PATH = f"/api/v1/quotingengine-service/cotizaciones/{COTIZACION_ID}"


def _transporte(*respuestas):
    llamadas: list[httpx.Request] = []
    pendientes = list(respuestas)

    def handler(request: httpx.Request) -> httpx.Response:
        llamadas.append(request)
        respuesta = pendientes.pop(0) if len(pendientes) > 1 else pendientes[0]
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta

    return httpx.MockTransport(handler), llamadas


def _cuerpo_cotizacion(**cambios):
    return {
        "cotizacion_id": str(COTIZACION_ID),
        "cliente_id": str(CLIENTE_ID),
        "estado": "VIGENTE",
        "prima_total": "1250000.50",
        "moneda": "COP",
        "expira_en": "2026-11-20T12:00:00Z",
        **cambios,
    }


async def test_obtiene_la_cotizacion_y_reenvia_el_correlation_id():
    transporte, llamadas = _transporte(httpx.Response(200, json=_cuerpo_cotizacion()))
    cliente = QuotingEngineHttpClient(BASE, transport=transporte)

    cotizacion = await cliente.obtener(COTIZACION_ID, CORRELACION)

    assert cotizacion.cliente_id == CLIENTE_ID and cotizacion.estado == "VIGENTE"
    assert cotizacion.prima_total == Decimal("1250000.50") and cotizacion.moneda == "COP"
    assert cotizacion.expira_en == datetime(2026, 11, 20, 12, tzinfo=UTC)
    assert llamadas[0].url.path == COTIZACION_PATH
    assert llamadas[0].headers["x-correlation-id"] == CORRELACION
    await cliente.aclose()


async def test_cotizacion_inexistente():
    transporte, _ = _transporte(httpx.Response(404, json={"detail": "no"}))

    with pytest.raises(CotizacionNoEncontradaError):
        await QuotingEngineHttpClient(BASE, transport=transporte).obtener(COTIZACION_ID, CORRELACION)


@pytest.mark.parametrize(
    "respuesta",
    [
        httpx.Response(500, json={"detail": "x"}),
        httpx.Response(200, text="no es json"),
        httpx.Response(200, json=[]),
        httpx.Response(200, json=_cuerpo_cotizacion(prima_total="abc")),
        httpx.Response(200, json=_cuerpo_cotizacion(expira_en="2026-11-20T12:00:00")),
        httpx.Response(200, json={"cotizacion_id": str(COTIZACION_ID)}),
        httpx.ConnectError("sin conexión"),
        httpx.ReadTimeout("lento"),
    ],
)
async def test_cotizacion_con_servicio_caido_o_respuesta_invalida(respuesta):
    transporte, _ = _transporte(respuesta)

    with pytest.raises(ServicioNoDisponibleError):
        await QuotingEngineHttpClient(BASE, transport=transporte).obtener(COTIZACION_ID, CORRELACION)


@pytest.mark.parametrize(
    ("respuesta", "esperado"),
    [
        (httpx.Response(200, json={"ultima_decision": {"decision": "ACEPTADA"}}), True),
        (httpx.Response(200, json={"ultima_decision": {"decision": "RECHAZADA"}}), False),
        (httpx.Response(200, json={"ultima_decision": None}), False),
        (httpx.Response(200, json={}), False),
        (httpx.Response(404, json={"detail": "x"}), False),
    ],
)
async def test_condiciones_aceptadas_segun_la_ultima_decision(respuesta, esperado):
    transporte, llamadas = _transporte(respuesta)
    cliente = QuotingEngineHttpClient(BASE, transport=transporte)

    assert await cliente.condiciones_aceptadas(COTIZACION_ID, CORRELACION) is esperado
    assert llamadas[0].url.path == f"{COTIZACION_PATH}/condiciones"


async def test_condiciones_con_servicio_caido():
    transporte, _ = _transporte(httpx.Response(503, json={}))

    with pytest.raises(ServicioNoDisponibleError):
        await QuotingEngineHttpClient(BASE, transport=transporte).condiciones_aceptadas(
            COTIZACION_ID, CORRELACION
        )


async def test_obtiene_la_firma_vigente():
    firma_id = uuid.uuid4()
    transporte, llamadas = _transporte(
        httpx.Response(
            200, json={"firma_id": str(firma_id), "cliente_id": str(CLIENTE_ID), "estado": "CAPTURADA"}
        )
    )
    cliente = InsurancePoliciesHttpClient(BASE, transport=transporte)

    firma = await cliente.obtener_vigente(COTIZACION_ID, CORRELACION)

    assert (firma.firma_id, firma.cliente_id, firma.estado) == (firma_id, CLIENTE_ID, "CAPTURADA")
    assert llamadas[0].url.path == (
        f"/api/v1/insurancepolicies-service/cotizaciones/{COTIZACION_ID}/firma-digital"
    )
    assert llamadas[0].headers["x-correlation-id"] == CORRELACION
    await cliente.aclose()


async def test_sin_firma_vigente_devuelve_none():
    transporte, _ = _transporte(httpx.Response(404, json={"detail": {"codigo": "FIRMA_NO_ENCONTRADA"}}))

    assert await InsurancePoliciesHttpClient(BASE, transport=transporte).obtener_vigente(
        COTIZACION_ID, CORRELACION
    ) is None


@pytest.mark.parametrize(
    "respuesta", [httpx.Response(500, json={}), httpx.Response(200, json={"firma_id": "x"}), httpx.ConnectError("x")]
)
async def test_firma_con_servicio_caido_o_respuesta_invalida(respuesta):
    transporte, _ = _transporte(respuesta)

    with pytest.raises(ServicioNoDisponibleError):
        await InsurancePoliciesHttpClient(BASE, transport=transporte).obtener_vigente(
            COTIZACION_ID, CORRELACION
        )


def _cobro(credencial):
    return SolicitudCobro(
        referencia="pago-1",
        monto=Decimal("99000.00"),
        moneda="COP",
        credencial=credencial,
        correlation_id=CORRELACION,
    )


@pytest.mark.parametrize(
    ("respuesta", "aprobado", "codigo"),
    [
        ({"id": "PAYPAL_1", "status": "COMPLETED", "failure_code": None}, True, None),
        ({"id": "PAYPAL_2", "status": "DECLINED", "failure_code": "INSUFFICIENT_FUNDS"}, False, "INSUFFICIENT_FUNDS"),
    ],
)
async def test_paypal_envia_el_pago_con_idempotencia(respuesta, aprobado, codigo):
    transporte, llamadas = _transporte(httpx.Response(201, json=respuesta))
    cliente = ClienteProveedorPago(BASE, transport=transporte)

    resultado = await PayPalProveedor(cliente).cobrar(_cobro("cliente@example.com"))

    assert (resultado.aprobado, resultado.referencia, resultado.codigo_rechazo) == (
        aprobado,
        respuesta["id"],
        codigo,
    )
    peticion = llamadas[0]
    assert (peticion.method, peticion.url.path) == ("POST", "/paypal/payments")
    assert json.loads(peticion.content) == {
        "payer_email": "cliente@example.com",
        "amount": "99000.00",
        "currency": "COP",
        "reference": "pago-1",
    }
    assert peticion.headers["idempotency-key"] == "pago-1"
    assert peticion.headers["x-correlation-id"] == CORRELACION
    await cliente.aclose()


async def test_tarjeta_envia_el_token_y_devuelve_marca_y_ultimos_4():
    transporte, llamadas = _transporte(
        httpx.Response(
            201,
            json={"id": "ch_1", "status": "succeeded", "failure_code": None, "brand": "VISA", "last4": "4242"},
        )
    )

    resultado = await TarjetaCreditoProveedor(ClienteProveedorPago(BASE, transport=transporte)).cobrar(
        _cobro("tok_VISA_4242")
    )

    assert resultado.aprobado is True and resultado.referencia == "ch_1"
    assert (resultado.tarjeta_ultimos4, resultado.tarjeta_marca) == ("4242", "VISA")
    assert llamadas[0].url.path == "/credit-card/charges"
    assert json.loads(llamadas[0].content)["token"] == "tok_VISA_4242"


async def test_tokenizacion_envia_datos_al_mock_y_recibe_el_token():
    transporte, llamadas = _transporte(
        httpx.Response(201, json={"token": "tok_VISA_4242", "brand": "VISA", "last4": "4242"})
    )
    cliente = ClienteProveedorPago(BASE, transport=transporte)

    token = await TarjetaCreditoProveedor(cliente).tokenizar(
        DatosTarjeta("4242424242424242", 12, 2099, "123"), CORRELACION
    )

    assert token == "tok_VISA_4242"
    assert llamadas[0].url.path == "/credit-card/tokens"
    assert llamadas[0].headers["x-correlation-id"] == CORRELACION
    assert json.loads(llamadas[0].content) == {
        "number": "4242424242424242", "exp_month": 12, "exp_year": 2099, "cvv": "123"
    }
    await cliente.aclose()


@pytest.mark.parametrize(
    ("respuesta", "error", "codigo"),
    [
        (httpx.Response(422, json={}), SolicitudInvalidaError, "PROVEEDOR_HTTP_422"),
        (httpx.Response(500, json={}), ProveedorPagoError, "PROVEEDOR_HTTP_500"),
        (httpx.Response(201, text="no es json"), ProveedorPagoError, "RESPUESTA_INVALIDA"),
        (httpx.Response(201, json={"id": "ch_1"}), ProveedorPagoError, "RESPUESTA_INVALIDA"),
        (httpx.Response(201, json={"token": "4242424242424242"}), ProveedorPagoError, "RESPUESTA_INVALIDA"),
        (httpx.Response(201, json={"token": None}), ProveedorPagoError, "RESPUESTA_INVALIDA"),
        (httpx.ReadTimeout("lento"), ProveedorPagoError, "PROVEEDOR_NO_DISPONIBLE"),
    ],
)
async def test_errores_en_tokenizacion(respuesta, error, codigo):
    transporte, _ = _transporte(respuesta)
    cliente = ClienteProveedorPago(BASE, transport=transporte)

    with pytest.raises(error) as exc:
        await TarjetaCreditoProveedor(cliente).tokenizar(
            DatosTarjeta("4242424242424242", 12, 2099, "123"), CORRELACION
        )
    assert exc.value.codigo == codigo
    await cliente.aclose()


async def test_tarjeta_rechazada_por_el_proveedor():
    transporte, _ = _transporte(
        httpx.Response(201, json={"id": "ch_2", "status": "declined", "failure_code": "card_declined"})
    )

    resultado = await TarjetaCreditoProveedor(ClienteProveedorPago(BASE, transport=transporte)).cobrar(
        _cobro("tok_VISA_0002")
    )

    assert (resultado.aprobado, resultado.codigo_rechazo) == (False, "card_declined")


@pytest.mark.parametrize("proveedor", [PayPalProveedor, TarjetaCreditoProveedor])
async def test_errores_del_proveedor(proveedor):
    casos = [
        (httpx.Response(422, json={"detail": "x"}), SolicitudInvalidaError, "PROVEEDOR_HTTP_422"),
        (httpx.Response(500, json={}), ProveedorPagoError, "PROVEEDOR_HTTP_500"),
        (httpx.Response(201, text="no es json"), ProveedorPagoError, "RESPUESTA_INVALIDA"),
        (httpx.Response(201, json={"status": "COMPLETED"}), ProveedorPagoError, "RESPUESTA_INVALIDA"),
        (httpx.Response(201, json={"id": "x", "status": "OTRO"}), ProveedorPagoError, "RESPUESTA_INVALIDA"),
        (httpx.ReadTimeout("lento"), ProveedorPagoError, "PROVEEDOR_NO_DISPONIBLE"),
        (httpx.ConnectError("caído"), ProveedorPagoError, "PROVEEDOR_NO_DISPONIBLE"),
    ]
    for respuesta, error, codigo in casos:
        transporte, _ = _transporte(respuesta)
        with pytest.raises(error) as exc:
            await proveedor(ClienteProveedorPago(BASE, transport=transporte)).cobrar(_cobro("x"))
        assert exc.value.codigo == codigo
        # solo la solicitud inválida es definitiva; el resto es un resultado incierto
        assert isinstance(exc.value, SolicitudInvalidaError) == (error is SolicitudInvalidaError)
