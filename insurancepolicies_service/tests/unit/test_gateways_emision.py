import uuid
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from src.application.ports.cotizaciones import CotizacionNoEncontradaError
from src.application.ports.servicios import ServicioNoDisponibleError
from src.infrastructure.gateways.identity_http_client import IdentityHttpClient
from src.infrastructure.gateways.quotingengine_http_client import QuotingEngineHttpClient

COTIZACION_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
CLIENTE_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
PRODUCTO_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")
COBERTURA_ID = uuid.UUID("44444444-4444-4444-8444-444444444444")
BASE = "http://servicio"
COTIZACIONES = "/api/v1/quotingengine-service/cotizaciones"


def transporte(*respuestas):
    llamadas: list[httpx.Request] = []
    pendientes = list(respuestas)

    def handler(request: httpx.Request) -> httpx.Response:
        llamadas.append(request)
        respuesta = pendientes.pop(0) if len(pendientes) > 1 else pendientes[0]
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta

    return httpx.MockTransport(handler), llamadas


def cuerpo_cotizacion(**cambios):
    return {
        "cotizacion_id": str(COTIZACION_ID),
        "cliente_id": str(CLIENTE_ID),
        "producto_codigo": "VIDA_HIPOTECARIO",
        "estado": "VIGENTE",
        "moneda": "COP",
        "prima_base": "1000000.00",
        "prima_neta": "1190000.00",
        "impuestos": [{"concepto": "IVA", "tasa": "0.19", "valor": "226100.00"}],
        "prima_total": "1416100.00",
        "coberturas": [
            {
                "cobertura_id": str(COBERTURA_ID),
                "codigo": "FALLECIMIENTO",
                "nombre": "Fallecimiento",
                "prima": "1416100.00",
                "limite_asegurado": "200000000.00",
                "deducible": "0.00",
            }
        ],
        "expira_en": "2026-11-20T12:00:00Z",
        **cambios,
    }


async def test_lee_la_cotizacion_con_coberturas_e_impuestos():
    t, llamadas = transporte(httpx.Response(200, json=cuerpo_cotizacion()))
    cliente = QuotingEngineHttpClient(BASE, transport=t)

    cotizacion = await cliente.obtener_cotizacion(COTIZACION_ID, "corr-7")

    assert (cotizacion.cotizacion_id, cotizacion.cliente_id) == (COTIZACION_ID, CLIENTE_ID)
    assert cotizacion.producto_codigo == "VIDA_HIPOTECARIO" and cotizacion.moneda == "COP"
    assert cotizacion.prima_total == Decimal("1416100.00") and cotizacion.prima_neta == Decimal("1190000.00")
    (impuesto,) = cotizacion.impuestos
    assert (impuesto.concepto, impuesto.tasa, impuesto.valor) == ("IVA", Decimal("0.19"), Decimal("226100.00"))
    (cobertura,) = cotizacion.coberturas
    assert cobertura.cobertura_id == COBERTURA_ID and cobertura.limite_asegurado == Decimal("200000000.00")
    assert llamadas[0].url.path == f"{COTIZACIONES}/{COTIZACION_ID}"
    assert llamadas[0].headers["x-correlation-id"] == "corr-7"
    await cliente.aclose()


async def test_cotizacion_inexistente():
    t, _ = transporte(httpx.Response(404, json={"detail": "no"}))

    with pytest.raises(CotizacionNoEncontradaError):
        await QuotingEngineHttpClient(BASE, transport=t).obtener_cotizacion(COTIZACION_ID, "c")


@pytest.mark.parametrize(
    "respuesta",
    [
        httpx.Response(500, json={}),
        httpx.Response(200, text="no es json"),
        httpx.Response(200, json=[]),
        httpx.Response(200, json={"cotizacion_id": str(COTIZACION_ID)}),
        httpx.Response(200, json=cuerpo_cotizacion(prima_total="abc")),
        httpx.Response(200, json=cuerpo_cotizacion(coberturas=[{"codigo": "x"}])),
        httpx.ConnectError("sin conexión"),
        httpx.ReadTimeout("lento"),
    ],
)
async def test_cotizacion_con_servicio_caido_o_respuesta_invalida(respuesta):
    t, _ = transporte(respuesta)

    with pytest.raises(ServicioNoDisponibleError):
        await QuotingEngineHttpClient(BASE, transport=t).obtener_cotizacion(COTIZACION_ID, "c")


async def test_lee_el_producto():
    t, llamadas = transporte(
        httpx.Response(
            200,
            json={
                "producto_id": str(PRODUCTO_ID),
                "codigo": "VIDA_HIPOTECARIO",
                "nombre": "Seguro de Vida Deudores Hipotecarios",
                "ramo": "VIDA",
            },
        )
    )

    producto = await QuotingEngineHttpClient(BASE, transport=t).obtener_producto("VIDA_HIPOTECARIO", "c")

    assert (producto.producto_id, producto.ramo) == (PRODUCTO_ID, "VIDA")
    assert producto.nombre == "Seguro de Vida Deudores Hipotecarios"
    assert llamadas[0].url.path == "/api/v1/quotingengine-service/productos/VIDA_HIPOTECARIO"


@pytest.mark.parametrize(
    "respuesta", [httpx.Response(404, json={}), httpx.Response(200, json={"codigo": "x"})]
)
async def test_producto_inexistente_o_invalido(respuesta):
    t, _ = transporte(respuesta)

    with pytest.raises(ServicioNoDisponibleError):
        await QuotingEngineHttpClient(BASE, transport=t).obtener_producto("X", "c")


async def test_lee_condiciones_y_la_fecha_de_aceptacion():
    t, llamadas = transporte(
        httpx.Response(
            200,
            json={
                "version_condiciones_generales": "1.0",
                "condiciones_particulares": {"vigencia_propuesta": {"desde": "a", "hasta": "b"}},
                "ultima_decision": {"decision": "ACEPTADA", "decidida_en": "2026-11-12T19:00:00Z"},
            },
        )
    )

    condiciones = await QuotingEngineHttpClient(BASE, transport=t).obtener_condiciones(COTIZACION_ID, "c")

    assert condiciones.version_condiciones_generales == "1.0"
    assert condiciones.condiciones_particulares["vigencia_propuesta"] == {"desde": "a", "hasta": "b"}
    assert condiciones.aceptadas_en == datetime(2026, 11, 12, 19, tzinfo=UTC)
    assert llamadas[0].url.path == f"{COTIZACIONES}/{COTIZACION_ID}/condiciones"


@pytest.mark.parametrize(
    "decision", [None, {"decision": "RECHAZADA", "decidida_en": "2026-11-12T19:00:00Z"}]
)
async def test_sin_aceptacion_no_hay_fecha(decision):
    t, _ = transporte(
        httpx.Response(
            200,
            json={
                "version_condiciones_generales": "1.0",
                "condiciones_particulares": {},
                "ultima_decision": decision,
            },
        )
    )

    condiciones = await QuotingEngineHttpClient(BASE, transport=t).obtener_condiciones(COTIZACION_ID, "c")

    assert condiciones.aceptadas_en is None


@pytest.mark.parametrize(
    "respuesta",
    [
        httpx.Response(404, json={}),
        httpx.Response(200, json={"version_condiciones_generales": "1.0"}),
        httpx.Response(200, json={"version_condiciones_generales": "1.0", "condiciones_particulares": []}),
        httpx.Response(
            200,
            json={
                "version_condiciones_generales": "1.0",
                "condiciones_particulares": {},
                "ultima_decision": {"decision": "ACEPTADA", "decidida_en": "ayer"},
            },
        ),
    ],
)
async def test_condiciones_invalidas(respuesta):
    t, _ = transporte(respuesta)

    with pytest.raises(ServicioNoDisponibleError):
        await QuotingEngineHttpClient(BASE, transport=t).obtener_condiciones(COTIZACION_ID, "c")


async def test_lee_el_titular_del_perfil():
    t, llamadas = transporte(
        httpx.Response(
            200,
            json={
                "id": str(CLIENTE_ID),
                "nombres": "María Fernanda",
                "apellidos": "Rodríguez Castañeda",
                "tipo_documento": "CC",
                "numero_identificacion": "1020304050",
                "correo": "maria@example.com",
            },
        )
    )
    cliente = IdentityHttpClient(BASE, transport=t)

    titular = await cliente.obtener(CLIENTE_ID, "corr-3")

    assert titular.nombre_completo == "María Fernanda Rodríguez Castañeda"
    assert (titular.tipo_documento, titular.numero_identificacion) == ("CC", "1020304050")
    assert llamadas[0].url.path == f"/api/v1/identity-service/clientes/{CLIENTE_ID}/perfil"
    assert llamadas[0].headers["x-correlation-id"] == "corr-3"
    await cliente.aclose()


@pytest.mark.parametrize(
    "respuesta",
    [
        httpx.Response(403, json={"detail": "sin consentimiento"}),
        httpx.Response(404, json={}),
        httpx.Response(200, json={"nombres": "Solo nombre"}),
        httpx.Response(200, json=[]),
        httpx.ConnectError("caído"),
    ],
)
async def test_titular_no_disponible(respuesta):
    t, _ = transporte(respuesta)

    with pytest.raises(ServicioNoDisponibleError):
        await IdentityHttpClient(BASE, transport=t).obtener(CLIENTE_ID, "c")
