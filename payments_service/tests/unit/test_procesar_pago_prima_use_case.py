import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from pagos_fakes import (
    AHORA,
    CLIENTE_ID,
    COTIZACION_ID,
    CotizacionesFalsas,
    EventosEnMemoria,
    FirmasFalsas,
    ProveedorFalso,
    ProveedorTarjetaFalso,
    RepoPagosEnMemoria,
    Transaccion,
    cotizacion,
)

from src.application.ports.cotizaciones import CotizacionNoEncontradaError
from src.application.ports.proveedor_pago import (
    DatosTarjeta,
    ProveedorPagoError,
    ResultadoCobro,
    SolicitudInvalidaError,
)
from src.application.ports.servicios import ServicioNoDisponibleError
from src.application.use_cases.procesar_pago_prima_use_case import (
    CondicionesNoAceptadasError,
    CotizacionNoVigenteError,
    FirmaRequeridaError,
    IdempotencyKeyReutilizadaError,
    PagoEnCursoError,
    PagoYaAprobadoError,
    ProcesarPagoPrimaUseCase,
    SolicitudPago,
)
from src.domain.pagos.entities import EstadoPago, MetodoPago
from src.domain.pagos.repositories import PagoDuplicadoError

PAYPAL = SolicitudPago(COTIZACION_ID, CLIENTE_ID, MetodoPago.PAYPAL, "cliente@example.com")
TARJETA = SolicitudPago(
    COTIZACION_ID, CLIENTE_ID, MetodoPago.TARJETA_CREDITO, "",
    DatosTarjeta("4242424242424242", 12, 2099, "123"),
)
APROBADO = ResultadoCobro(aprobado=True, referencia="PP-1")
CORRELACION = "corr-1"


class Escenario:
    def __init__(self, *, proveedor=None, firmas=None, requiere_firma=True, **cotizaciones) -> None:
        self.ahora = AHORA
        self.pagos = RepoPagosEnMemoria()
        self.eventos = EventosEnMemoria()
        self.cotizaciones = CotizacionesFalsas(**cotizaciones)
        self.firmas = firmas or FirmasFalsas()
        self.paypal = proveedor or ProveedorFalso(APROBADO)
        self.tarjeta = ProveedorTarjetaFalso(
            ResultadoCobro(
                aprobado=True, referencia="ch_1", tarjeta_ultimos4="4242", tarjeta_marca="VISA"
            )
        )
        self.tx = Transaccion()
        self.caso = ProcesarPagoPrimaUseCase(
            self.pagos,
            self.eventos,
            self.cotizaciones,
            self.firmas,
            {MetodoPago.PAYPAL: self.paypal, MetodoPago.TARJETA_CREDITO: self.tarjeta},
            "mock_paymentprovider",
            self.tx.commit,
            self.tx.rollback,
            requiere_firma,
            timedelta(seconds=120),
            lambda: self.ahora,
        )

    async def pagar(self, solicitud=PAYPAL, clave="clave-1"):
        return await self.caso.ejecutar(solicitud, clave, CORRELACION)

    def pago_guardado(self):
        (pago,) = self.pagos.pagos.values()
        return pago


async def test_pago_aprobado_guarda_el_monto_de_la_cotizacion_y_publica_el_evento():
    e = Escenario()

    resultado = await e.pagar()

    assert resultado.creado is True
    pago = e.pago_guardado()
    assert pago.estado == EstadoPago.APROBADO
    assert resultado.pago.estado == EstadoPago.APROBADO
    assert pago.monto == Decimal("1250000.51")
    assert (pago.moneda, pago.proveedor_referencia, pago.codigo_rechazo) == ("COP", "PP-1", None)
    assert pago.procesado_en == AHORA and pago.version == 2
    (solicitud,) = e.paypal.solicitudes
    assert solicitud.referencia == str(pago.pago_id)
    assert (solicitud.monto, solicitud.moneda) == (pago.monto, "COP")
    assert (solicitud.credencial, solicitud.correlation_id) == ("cliente@example.com", CORRELACION)
    (evento,) = e.eventos.eventos
    assert evento.tipo == "PagoAprobado" and evento.agregado_id == pago.pago_id
    assert evento.payload["datos"] == {
        "pago_id": str(pago.pago_id),
        "cotizacion_id": str(COTIZACION_ID),
        "cliente_id": str(CLIENTE_ID),
        "monto": "1250000.51",
        "moneda": "COP",
        "metodo_pago": "PAYPAL",
        "proveedor_referencia": "PP-1",
    }
    assert evento.payload["evento_id"] == str(evento.evento_id)
    assert evento.payload["correlation_id"] == CORRELACION
    assert e.tx.commits == 2 and e.tx.rollbacks == 0


async def test_pago_con_tarjeta_guarda_marca_y_ultimos_4_sin_datos_sensibles():
    e = Escenario()

    resultado = await e.pagar(TARJETA)

    pago = resultado.pago
    assert (pago.metodo_pago, pago.tarjeta_ultimos4, pago.tarjeta_marca) == (
        MetodoPago.TARJETA_CREDITO,
        "4242",
        "VISA",
    )
    assert e.tarjeta.solicitudes[0].credencial == "tok_VISA_4242"
    assert e.paypal.solicitudes == []
    assert "tok_VISA_4242" not in repr(e.tarjeta.solicitudes[0])
    assert "tok_VISA_4242" not in repr(pago)
    assert "4242424242424242" not in repr(TARJETA)
    assert "123" not in repr(TARJETA.tarjeta)


async def test_reintento_con_tarjeta_tokeniza_de_nuevo_sin_cobrar_dos_veces():
    e = Escenario()
    primero = await e.pagar(TARJETA)

    repetido = await e.pagar(TARJETA)

    assert repetido.creado is False and repetido.pago.pago_id == primero.pago.pago_id
    assert len(e.tarjeta.tokenizaciones) == 2 and len(e.tarjeta.solicitudes) == 1


async def test_reintento_con_otra_tarjeta_rechaza_la_clave_reutilizada():
    e = Escenario()
    await e.pagar(TARJETA)
    otra = SolicitudPago(
        COTIZACION_ID, CLIENTE_ID, MetodoPago.TARJETA_CREDITO, "",
        DatosTarjeta("4000000000000002", 12, 2099, "123"),
    )

    with pytest.raises(IdempotencyKeyReutilizadaError):
        await e.pagar(otra)
    assert len(e.tarjeta.solicitudes) == 1


async def test_tokenizacion_no_disponible_no_crea_pago():
    e = Escenario()
    e.tarjeta.error_tokenizacion = ProveedorPagoError("PROVEEDOR_NO_DISPONIBLE")

    with pytest.raises(ProveedorPagoError):
        await e.pagar(TARJETA)
    assert e.pagos.pagos == {} and e.tarjeta.solicitudes == []


async def test_pago_rechazado_no_publica_evento_y_libera_la_cotizacion():
    e = Escenario(
        proveedor=ProveedorFalso(
            ResultadoCobro(aprobado=False, referencia="PP-2", codigo_rechazo="INSUFFICIENT_FUNDS")
        )
    )

    resultado = await e.pagar()

    assert resultado.pago.estado == EstadoPago.RECHAZADO
    assert resultado.pago.codigo_rechazo == "INSUFFICIENT_FUNDS"
    assert e.eventos.eventos == []
    # un rechazo no bloquea un nuevo intento con otra clave
    segundo = await e.pagar(clave="clave-2")
    assert segundo.creado is True and len(e.pagos.pagos) == 2


async def test_rechazo_sin_codigo_usa_un_codigo_generico():
    e = Escenario(proveedor=ProveedorFalso(ResultadoCobro(aprobado=False, referencia="x")))

    assert (await e.pagar()).pago.codigo_rechazo == "RECHAZADO_POR_PROVEEDOR"


async def test_solicitud_invalida_del_proveedor_se_rechaza_sin_cobrar():
    e = Escenario(proveedor=ProveedorFalso(SolicitudInvalidaError("PROVEEDOR_HTTP_422")))

    resultado = await e.pagar()

    assert resultado.pago.estado == EstadoPago.RECHAZADO
    assert resultado.pago.codigo_rechazo == "SOLICITUD_INVALIDA"
    assert e.eventos.eventos == []


async def test_reintento_con_la_misma_clave_devuelve_el_pago_sin_cobrar_de_nuevo():
    e = Escenario()
    primero = await e.pagar()

    repetido = await e.pagar()

    assert repetido.creado is False
    assert repetido.pago.pago_id == primero.pago.pago_id
    assert len(e.paypal.solicitudes) == 1 and len(e.eventos.eventos) == 1


async def test_reintento_no_revalida_la_cotizacion_vencida():
    e = Escenario()
    await e.pagar()
    e.cotizaciones.cotizacion = cotizacion(estado="EXPIRADA")

    assert (await e.pagar()).creado is False


async def test_misma_clave_con_otra_solicitud_es_conflicto():
    e = Escenario()
    await e.pagar()

    for otra in (TARJETA, SolicitudPago(COTIZACION_ID, CLIENTE_ID, MetodoPago.PAYPAL, "otro@example.com")):
        with pytest.raises(IdempotencyKeyReutilizadaError):
            await e.pagar(otra)


async def test_misma_clave_con_otro_medio_no_depende_de_tokenizacion():
    e = Escenario()
    await e.pagar()
    e.tarjeta.error_tokenizacion = ProveedorPagoError("PROVEEDOR_NO_DISPONIBLE")

    with pytest.raises(IdempotencyKeyReutilizadaError):
        await e.pagar(TARJETA)
    assert e.tarjeta.tokenizaciones == []


@pytest.mark.parametrize(
    ("cambios", "error"),
    [
        ({"estado": "EXPIRADA"}, CotizacionNoVigenteError),
        ({"expira_en": AHORA}, CotizacionNoVigenteError),
        ({"cliente_id": uuid.uuid4()}, CotizacionNoEncontradaError),
    ],
)
async def test_valida_la_cotizacion(cambios, error):
    e = Escenario(cotizacion_=cotizacion(**cambios))

    with pytest.raises(error):
        await e.pagar()

    assert e.pagos.pagos == {} and e.paypal.solicitudes == []


async def test_exige_condiciones_aceptadas():
    e = Escenario(aceptadas=False)

    with pytest.raises(CondicionesNoAceptadasError):
        await e.pagar()

    assert e.pagos.pagos == {}


async def test_exige_firma_digital_del_cliente():
    from src.application.ports.firmas import FirmaPago

    for firma in (None, FirmaPago(uuid.uuid4(), uuid.uuid4(), "CAPTURADA")):
        e = Escenario(firmas=FirmasFalsas(firma))
        with pytest.raises(FirmaRequeridaError):
            await e.pagar()
        assert e.pagos.pagos == {}


async def test_la_firma_puede_dejar_de_exigirse():
    firmas = FirmasFalsas(None)
    e = Escenario(firmas=firmas, requiere_firma=False)

    assert (await e.pagar()).pago.estado == EstadoPago.APROBADO
    assert firmas.llamadas == 0


async def test_falla_del_servicio_dependiente_no_crea_pago():
    e = Escenario()
    e.cotizaciones.error = ServicioNoDisponibleError("quotingengine_service")

    with pytest.raises(ServicioNoDisponibleError):
        await e.pagar()

    assert e.pagos.pagos == {}


async def test_pago_aprobado_de_la_cotizacion_bloquea_otro_pago():
    e = Escenario()
    await e.pagar()

    with pytest.raises(PagoYaAprobadoError):
        await e.pagar(TARJETA, clave="clave-2")

    assert len(e.paypal.solicitudes) == 1 and e.tarjeta.solicitudes == []


async def test_proveedor_caido_deja_el_pago_en_error_y_el_reintento_lo_resuelve():
    e = Escenario(
        proveedor=ProveedorFalso(ProveedorPagoError("PROVEEDOR_NO_DISPONIBLE"), APROBADO)
    )
    with pytest.raises(ProveedorPagoError):
        await e.pagar()
    pago = e.pago_guardado()
    assert (pago.estado, pago.error_codigo) == (EstadoPago.ERROR, "PROVEEDOR_NO_DISPONIBLE")
    assert e.eventos.eventos == []

    # con otra clave no se permite: el primer cobro pudo haberse realizado
    with pytest.raises(PagoEnCursoError):
        await e.pagar(clave="clave-2")

    resultado = await e.pagar()

    assert resultado.creado is False and resultado.pago.estado == EstadoPago.APROBADO
    assert resultado.pago.error_codigo is None
    # misma referencia ante el proveedor: no puede cobrar dos veces
    assert [s.referencia for s in e.paypal.solicitudes] == [str(pago.pago_id)] * 2
    assert len(e.eventos.eventos) == 1 and len(e.pagos.pagos) == 1


async def test_error_inesperado_deja_el_pago_en_error():
    e = Escenario(proveedor=ProveedorFalso(RuntimeError("boom")))

    with pytest.raises(ProveedorPagoError) as exc:
        await e.pagar()

    assert exc.value.codigo == "ERROR_INESPERADO"
    assert e.pago_guardado().estado == EstadoPago.ERROR


async def test_pago_pendiente_reciente_esta_en_curso_y_el_abandonado_se_reintenta():
    e = Escenario(proveedor=ProveedorFalso(ProveedorPagoError("PROVEEDOR_NO_DISPONIBLE"), APROBADO))
    with pytest.raises(ProveedorPagoError):
        await e.pagar()
    pago = e.pagos.pagos[e.pago_guardado().pago_id]
    pago.estado = EstadoPago.PENDIENTE
    pago.actualizado_en = e.ahora

    with pytest.raises(PagoEnCursoError):
        await e.pagar()
    e.ahora += timedelta(seconds=121)

    assert (await e.pagar()).pago.estado == EstadoPago.APROBADO


async def test_carrera_con_la_misma_clave_devuelve_el_pago_ganador():
    e = Escenario()
    ganador = await Escenario().pagar()
    e.pagos.pagos[ganador.pago.pago_id] = ganador.pago
    original = e.pagos.obtener_por_idempotency_key

    llamadas = []

    async def sin_pago_al_inicio(cliente_id, clave):
        llamadas.append(1)
        return None if len(llamadas) == 1 else await original(cliente_id, clave)

    e.pagos.obtener_por_idempotency_key = sin_pago_al_inicio
    e.pagos.obtener_activo_por_cotizacion = _siempre_none

    async def crear_duplicado(pago):
        raise PagoDuplicadoError()

    e.pagos.crear = crear_duplicado

    resultado = await e.pagar()

    assert resultado.creado is False and resultado.pago.pago_id == ganador.pago.pago_id
    assert e.tx.rollbacks == 1 and e.paypal.solicitudes == []


async def _siempre_none(*_):
    return None


async def test_carrera_con_otra_clave_es_pago_en_curso():
    e = Escenario()
    llamadas = []

    async def activo_aparece_despues(cotizacion_id):
        llamadas.append(1)
        if len(llamadas) == 1:
            return None
        return await RepoPagosEnMemoria.obtener_activo_por_cotizacion(e.pagos, cotizacion_id)

    async def crear_duplicado(pago):
        raise PagoDuplicadoError()

    e.pagos.obtener_activo_por_cotizacion = activo_aparece_despues
    e.pagos.crear = crear_duplicado

    with pytest.raises(PagoEnCursoError):
        await e.pagar()

    assert e.tx.rollbacks == 1 and e.paypal.solicitudes == []


async def test_conflicto_de_version_al_guardar_el_resultado_no_publica_evento():
    e = Escenario()
    original = e.pagos.actualizar

    async def fallar_la_segunda(pago):
        return await original(pago) if pago.version == 0 else False

    e.pagos.actualizar = fallar_la_segunda

    with pytest.raises(PagoEnCursoError):
        await e.pagar()

    assert e.eventos.eventos == [] and e.tx.rollbacks == 1
