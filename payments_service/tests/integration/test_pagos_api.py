import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from pagos_fakes import (
    CLIENTE_ID,
    COTIZACION_ID,
    CotizacionesFalsas,
    FirmasFalsas,
    ProveedorFalso,
    ProveedorTarjetaFalso,
    cotizacion,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.proveedor_pago import (
    ProveedorPagoError,
    ResultadoCobro,
    SolicitudInvalidaError,
)
from src.application.ports.servicios import ServicioNoDisponibleError
from src.domain.pagos.entities import MetodoPago
from src.infrastructure.persistence.models import EventoOutboxModel, PagoPrimaModel
from src.main import app
from src.presentation.dependencies import (
    get_cotizacion_gateway,
    get_db,
    get_firma_gateway,
    get_proveedores_pago,
)

PREFIJO = "/api/v1/payments-service"
PAGOS = f"{PREFIJO}/pagos"
RESUMEN = f"{PREFIJO}/cotizaciones/{COTIZACION_ID}/resumen-pago"

PAYPAL = {
    "cotizacion_id": str(COTIZACION_ID),
    "cliente_id": str(CLIENTE_ID),
    "paypal_email": "cliente@example.com",
}
TARJETA = {
    "cotizacion_id": str(COTIZACION_ID),
    "cliente_id": str(CLIENTE_ID),
    "metodo_pago": "TARJETA_CREDITO",
    "numero_tarjeta": "4242424242424242",
    "mes_expiracion": 12,
    "anio_expiracion": 2099,
    "cvv": "123",
}


class Entorno:
    def __init__(self) -> None:
        self.cotizaciones = CotizacionesFalsas()
        self.firmas = FirmasFalsas()
        self.paypal = ProveedorFalso(ResultadoCobro(aprobado=True, referencia="PAYPAL_1"))
        self.tarjeta = ProveedorTarjetaFalso(
            ResultadoCobro(
                aprobado=True, referencia="ch_1", tarjeta_ultimos4="4242", tarjeta_marca="VISA"
            )
        )


@pytest.fixture
def entorno() -> Entorno:
    return Entorno()


@pytest.fixture
async def client(db_session: AsyncSession, entorno: Entorno) -> AsyncGenerator[AsyncClient, None]:
    async def _db():
        yield db_session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_cotizacion_gateway] = lambda: entorno.cotizaciones
    app.dependency_overrides[get_firma_gateway] = lambda: entorno.firmas
    app.dependency_overrides[get_proveedores_pago] = lambda: {
        MetodoPago.PAYPAL: entorno.paypal,
        MetodoPago.TARJETA_CREDITO: entorno.tarjeta,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


def _pagar(client: AsyncClient, cuerpo=PAYPAL, clave="clave-1", **headers):
    cabeceras = {"Idempotency-Key": clave} if clave else {}
    return client.post(PAGOS, json=cuerpo, headers={**cabeceras, **headers})


async def test_resumen_presenta_la_prima_y_paypal_por_defecto(client):
    response = await client.get(RESUMEN)

    assert response.status_code == 200
    assert response.json() == {
        "cotizacion_id": str(COTIZACION_ID),
        "prima_total": "1250000.505",
        "moneda": "COP",
        "expira_en": cotizacion().expira_en.isoformat().replace("+00:00", "Z"),
        "metodos_pago": [
            {"codigo": "PAYPAL", "por_defecto": True},
            {"codigo": "TARJETA_CREDITO", "por_defecto": False},
        ],
    }


@pytest.mark.parametrize(
    ("preparar", "status_esperado", "codigo"),
    [
        (lambda e: setattr(e.cotizaciones, "cotizacion", cotizacion(cotizacion_id=uuid.uuid4())), 404, "COTIZACION_NO_ENCONTRADA"),
        (lambda e: setattr(e.cotizaciones, "cotizacion", cotizacion(estado="EXPIRADA")), 409, "COTIZACION_NO_VIGENTE"),
        (lambda e: setattr(e.cotizaciones, "error", ServicioNoDisponibleError("x")), 503, "SERVICIO_NO_DISPONIBLE"),
    ],
)
async def test_resumen_errores(client, entorno, preparar, status_esperado, codigo):
    preparar(entorno)

    response = await client.get(RESUMEN)

    assert response.status_code == status_esperado
    assert response.json()["detail"]["codigo"] == codigo


async def test_pago_con_paypal_por_defecto_se_aprueba_y_deja_el_evento_en_el_outbox(
    client, entorno, db_session: AsyncSession
):
    response = await _pagar(client, **{"X-Correlation-Id": "corr-9"})

    assert response.status_code == 201
    cuerpo = response.json()
    assert cuerpo["estado"] == "APROBADO" and cuerpo["metodo_pago"] == "PAYPAL"
    assert (cuerpo["monto"], cuerpo["moneda"]) == ("1250000.51", "COP")
    assert cuerpo["cotizacion_id"] == str(COTIZACION_ID) and cuerpo["cliente_id"] == str(CLIENTE_ID)
    assert cuerpo["codigo_rechazo"] is None and cuerpo["procesado_en"]
    assert not {"idempotency_key", "hash_solicitud", "paypal_email", "credencial"} & set(cuerpo)
    assert entorno.cotizaciones.correlaciones == ["corr-9"]
    assert entorno.paypal.solicitudes[0].credencial == "cliente@example.com"

    pago = (await db_session.execute(select(PagoPrimaModel))).scalar_one()
    assert (pago.estado, pago.proveedor_referencia, pago.correlation_id) == ("APROBADO", "PAYPAL_1", "corr-9")
    evento = (await db_session.execute(select(EventoOutboxModel))).scalar_one()
    assert (evento.tipo, evento.estado, evento.agregado_id) == ("PagoAprobado", "PENDIENTE", pago.pago_id)
    assert evento.payload["datos"]["pago_id"] == cuerpo["pago_id"]
    assert evento.payload["datos"]["monto"] == "1250000.51"


async def test_pago_con_tarjeta(client, entorno, db_session: AsyncSession):
    response = await _pagar(client, TARJETA)

    assert response.status_code == 201
    cuerpo = response.json()
    assert (cuerpo["estado"], cuerpo["metodo_pago"]) == ("APROBADO", "TARJETA_CREDITO")
    assert (cuerpo["tarjeta_ultimos4"], cuerpo["tarjeta_marca"]) == ("4242", "VISA")
    assert "tok_VISA_4242" not in response.text
    assert "4242424242424242" not in response.text
    assert "cvv" not in cuerpo
    assert entorno.paypal.solicitudes == []
    pago = (await db_session.execute(select(PagoPrimaModel))).scalar_one()
    evento = (await db_session.execute(select(EventoOutboxModel))).scalar_one()
    for valor in ("4242424242424242", "tok_VISA_4242", '"cvv"'):
        assert valor not in str(vars(pago))
        assert valor not in str(evento.payload)
    assert 2099 not in vars(pago).values()


async def test_reintento_con_tarjeta_reutiliza_pago_sin_cobro_adicional(client, entorno):
    primero = await _pagar(client, TARJETA)
    repetido = await _pagar(client, TARJETA)

    assert (primero.status_code, repetido.status_code) == (201, 200)
    assert primero.json() == repetido.json()
    assert len(entorno.tarjeta.tokenizaciones) == 2
    assert len(entorno.tarjeta.solicitudes) == 1


async def test_reintento_con_pasarela_caida_no_repite_el_cobro(client, entorno):
    primero = await _pagar(client, TARJETA)
    entorno.tarjeta.error_tokenizacion = ProveedorPagoError("PROVEEDOR_NO_DISPONIBLE")
    fallido = await _pagar(client, TARJETA)
    entorno.tarjeta.error_tokenizacion = None
    repetido = await _pagar(client, TARJETA)

    assert (primero.status_code, fallido.status_code, repetido.status_code) == (201, 503, 200)
    assert primero.json() == repetido.json()
    assert len(entorno.tarjeta.solicitudes) == 1


@pytest.mark.parametrize(
    ("error", "status_code", "codigo"),
    [
        (SolicitudInvalidaError("PROVEEDOR_HTTP_422"), 422, "SOLICITUD_INVALIDA"),
        (ProveedorPagoError("PROVEEDOR_NO_DISPONIBLE"), 503, "PROVEEDOR_PAGO_NO_DISPONIBLE"),
    ],
)
async def test_error_de_tokenizacion_no_crea_pago(client, entorno, db_session, error, status_code, codigo):
    entorno.tarjeta.error_tokenizacion = error

    response = await _pagar(client, TARJETA)

    assert (response.status_code, response.json()["detail"]["codigo"]) == (status_code, codigo)
    assert (await db_session.execute(select(PagoPrimaModel))).first() is None
    assert entorno.tarjeta.solicitudes == []
    assert TARJETA["numero_tarjeta"] not in response.text


async def test_pago_rechazado_responde_201_sin_evento(client, entorno, db_session: AsyncSession):
    entorno.tarjeta.respuestas = [
        ResultadoCobro(aprobado=False, referencia="ch_2", codigo_rechazo="insufficient_funds")
    ]

    response = await _pagar(client, TARJETA)

    assert response.status_code == 201
    assert (response.json()["estado"], response.json()["codigo_rechazo"]) == ("RECHAZADO", "insufficient_funds")
    assert (await db_session.execute(select(EventoOutboxModel))).first() is None
    # la cotización queda libre para pagar con otro medio
    segundo = await _pagar(client, clave="clave-2")
    assert segundo.status_code == 201 and segundo.json()["estado"] == "APROBADO"


async def test_reintento_idempotente_devuelve_200_y_no_cobra_dos_veces(
    client, entorno, db_session: AsyncSession
):
    primero = await _pagar(client)
    repetido = await _pagar(client)

    assert (primero.status_code, repetido.status_code) == (201, 200)
    assert repetido.json() == primero.json()
    assert len(entorno.paypal.solicitudes) == 1
    assert len((await db_session.execute(select(EventoOutboxModel))).scalars().all()) == 1


async def test_clave_reutilizada_con_otro_medio_es_conflicto(client):
    await _pagar(client)

    response = await _pagar(client, TARJETA)

    assert (response.status_code, response.json()["detail"]["codigo"]) == (409, "IDEMPOTENCY_KEY_REUTILIZADA")


async def test_no_permite_pagar_dos_veces_la_misma_prima(client):
    await _pagar(client)

    response = await _pagar(client, TARJETA, clave="clave-2")

    assert (response.status_code, response.json()["detail"]["codigo"]) == (409, "PAGO_YA_APROBADO")


@pytest.mark.parametrize(
    ("preparar", "status_esperado", "codigo"),
    [
        (lambda e: setattr(e.cotizaciones, "cotizacion", cotizacion(cotizacion_id=uuid.uuid4())), 404, "COTIZACION_NO_ENCONTRADA"),
        (lambda e: setattr(e.cotizaciones, "cotizacion", cotizacion(cliente_id=uuid.uuid4())), 404, "COTIZACION_NO_ENCONTRADA"),
        (lambda e: setattr(e.cotizaciones, "cotizacion", cotizacion(estado="EXPIRADA")), 409, "COTIZACION_NO_VIGENTE"),
        (lambda e: setattr(e.cotizaciones, "aceptadas", False), 409, "CONDICIONES_NO_ACEPTADAS"),
        (lambda e: setattr(e.firmas, "firma", None), 409, "FIRMA_REQUERIDA"),
        (lambda e: setattr(e.cotizaciones, "error", ServicioNoDisponibleError("x")), 503, "SERVICIO_NO_DISPONIBLE"),
    ],
)
async def test_precondiciones_del_pago(client, entorno, preparar, status_esperado, codigo):
    preparar(entorno)

    response = await _pagar(client)

    assert (response.status_code, response.json()["detail"]["codigo"]) == (status_esperado, codigo)
    assert entorno.paypal.solicitudes == []


async def test_pasarela_caida_responde_503_y_el_reintento_con_la_misma_clave_lo_resuelve(
    client, entorno, db_session: AsyncSession
):
    entorno.paypal.respuestas = [
        ProveedorPagoError("PROVEEDOR_NO_DISPONIBLE"),
        ResultadoCobro(aprobado=True, referencia="PAYPAL_1"),
    ]

    fallido = await _pagar(client)
    assert (fallido.status_code, fallido.json()["detail"]["codigo"]) == (503, "PROVEEDOR_PAGO_NO_DISPONIBLE")
    pago = (await db_session.execute(select(PagoPrimaModel))).scalar_one()
    assert (pago.estado, pago.error_codigo) == ("ERROR", "PROVEEDOR_NO_DISPONIBLE")

    en_curso = await _pagar(client, clave="clave-2")
    assert (en_curso.status_code, en_curso.json()["detail"]["codigo"]) == (409, "PAGO_EN_CURSO")

    reintento = await _pagar(client)
    assert reintento.status_code == 200 and reintento.json()["estado"] == "APROBADO"
    assert [s.referencia for s in entorno.paypal.solicitudes] == [str(pago.pago_id)] * 2


async def test_solicitud_invalida_de_la_pasarela_se_registra_como_rechazo(client, entorno):
    entorno.tarjeta.respuestas = [SolicitudInvalidaError("PROVEEDOR_HTTP_422")]

    response = await _pagar(client, TARJETA)

    assert response.status_code == 201
    assert (response.json()["estado"], response.json()["codigo_rechazo"]) == ("RECHAZADO", "SOLICITUD_INVALIDA")


@pytest.mark.parametrize("clave", [None, "", "con espacios", "x" * 101])
async def test_exige_una_clave_de_idempotencia_valida(client, clave):
    response = await _pagar(client, clave=clave)

    assert response.status_code == 422
    assert response.json()["detail"]["codigo"] == "IDEMPOTENCY_KEY_INVALIDA"


@pytest.mark.parametrize(
    "cuerpo",
    [
        {**PAYPAL, "paypal_email": None},
        {**PAYPAL, "paypal_email": "sin-arroba"},
        {**PAYPAL, "tarjeta_token": "tok_VISA_4242"},
        {**TARJETA, "numero_tarjeta": None},
        {**TARJETA, "numero_tarjeta": "123"},
        {**TARJETA, "mes_expiracion": 13},
        {**TARJETA, "mes_expiracion": True},
        {**TARJETA, "anio_expiracion": 1999},
        {**TARJETA, "anio_expiracion": "2099"},
        {**TARJETA, "cvv": "12"},
        {**TARJETA, "tarjeta_token": "tok_VISA_4242"},
        {**TARJETA, "paypal_email": "cliente@example.com"},
        {**PAYPAL, "metodo_pago": "EFECTIVO"},
        {**PAYPAL, "monto": "1"},
        {**PAYPAL, "cotizacion_id": "no-es-uuid"},
        {"cliente_id": str(CLIENTE_ID), "paypal_email": "cliente@example.com"},
    ],
)
async def test_valida_los_datos_del_medio_de_pago(client, entorno, cuerpo):
    response = await _pagar(client, cuerpo)

    assert response.status_code == 422
    assert "4242424242424242" not in response.text
    assert '"input"' not in response.text
    assert entorno.paypal.solicitudes == [] and entorno.tarjeta.solicitudes == []


async def test_errores_no_devuelven_datos_sensibles(client):
    response = await _pagar(client, {**TARJETA, "cvv": "987", "mes_expiracion": 13})

    assert response.status_code == 422
    assert "4242424242424242" not in response.text
    assert "987" not in response.text
    assert "2099" not in response.text
    assert response.json()["detail"][0]["loc"] == ["body", "mes_expiracion"]


async def test_consulta_un_pago(client):
    pago_id = (await _pagar(client)).json()["pago_id"]

    response = await client.get(f"{PAGOS}/{pago_id}")

    assert response.status_code == 200 and response.json()["pago_id"] == pago_id
    assert response.json()["estado"] == "APROBADO"


async def test_consulta_de_pago_inexistente(client):
    response = await client.get(f"{PAGOS}/{uuid.uuid4()}")

    assert (response.status_code, response.json()["detail"]["codigo"]) == (404, "PAGO_NO_ENCONTRADO")
