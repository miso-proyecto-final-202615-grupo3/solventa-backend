import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from emision_fakes import (
    AHORA,
    CLIENTE_ID,
    COBERTURA_ID,
    COTIZACION_ID,
    PRODUCTO_ID,
    CotizacionesFalsas,
    EventosEnMemoria,
    FirmasEnMemoria,
    PolizasEnMemoria,
    TitularesFalsos,
    Transaccion,
    cotizacion,
    firma,
)

from src.application.ports.cotizaciones import CondicionesEmision, CotizacionNoEncontradaError
from src.application.ports.servicios import ServicioNoDisponibleError
from src.application.use_cases.emitir_poliza_use_case import (
    DatosEmisionInvalidosError,
    EmitirPolizaUseCase,
    FirmaRequeridaError,
    PagoInconsistenteError,
    numero_de_poliza,
)
from src.domain.eventos.mensajes import PagoAprobado, PolizaEmitida
from src.domain.firmas.entities import EstadoFirma
from src.domain.polizas.entities import EstadoCertificado
from src.domain.polizas.repositories import PolizaDuplicadaError

PAGO = PagoAprobado(
    evento_id="evt-1",
    pago_id=uuid.uuid4(),
    cotizacion_id=COTIZACION_ID,
    cliente_id=CLIENTE_ID,
    monto=Decimal("1416100.00"),
    moneda="COP",
    metodo_pago="PAYPAL",
    proveedor_referencia="PAYPAL_1",
    correlation_id="corr-1",
)


class Escenario:
    def __init__(self, firma_vigente=True) -> None:
        self.firma = firma()
        self.polizas = PolizasEnMemoria()
        self.firmas = FirmasEnMemoria(self.firma) if firma_vigente else FirmasEnMemoria()
        self.eventos = EventosEnMemoria()
        self.cotizaciones = CotizacionesFalsas()
        self.titulares = TitularesFalsos()
        self.tx = Transaccion()
        self.caso = EmitirPolizaUseCase(
            self.polizas,
            self.firmas,
            self.eventos,
            self.cotizaciones,
            self.titulares,
            self.tx.commit,
            self.tx.rollback,
            ahora=lambda: AHORA,
            generar_numero=lambda emitida_en: "POL-20261113-AAAA0001",
        )

    async def emitir(self, pago=PAGO):
        return await self.caso.ejecutar(pago, "corr-1")


async def test_emite_la_poliza_con_los_datos_de_la_cotizacion_y_el_titular():
    e = Escenario()

    resultado = await e.emitir()

    assert resultado.creada is True
    poliza = e.polizas.polizas[resultado.poliza.poliza_id]
    assert poliza.numero == "POL-20261113-AAAA0001" and poliza.estado == "EMITIDA"
    assert poliza.estado_certificado == EstadoCertificado.PENDIENTE and poliza.ruta_certificado is None
    assert (poliza.cliente_id, poliza.cotizacion_id) == (CLIENTE_ID, COTIZACION_ID)
    assert poliza.producto_id == PRODUCTO_ID and poliza.ramo == "VIDA"
    assert poliza.titular_nombre == "María Fernanda Rodríguez Castañeda"
    assert poliza.emitida_en == AHORA
    assert poliza.vigencia_desde == datetime(2026, 11, 13, 13, tzinfo=UTC)
    assert poliza.vigencia_hasta == datetime(2036, 11, 13, 13, tzinfo=UTC)
    (cobertura,) = poliza.coberturas
    assert cobertura.cobertura_id == COBERTURA_ID and cobertura.poliza_id == poliza.poliza_id
    assert cobertura.prima == Decimal("1416100.00")
    assert poliza.prima_total == Decimal("1416100.00")
    assert e.tx.commits == 1 and e.tx.rollbacks == 0


async def test_guarda_la_instantanea_del_contrato_para_el_certificado():
    e = Escenario()

    resultado = await e.emitir()

    datos = e.polizas.contratos[resultado.poliza.poliza_id].datos
    assert datos["moneda"] == "COP"
    assert datos["titular"] == {
        "nombre": "María Fernanda Rodríguez Castañeda",
        "tipo_documento": "CC",
        "numero_identificacion": "1020304050",
    }
    assert datos["producto"]["nombre"] == "Seguro de Vida Deudores Hipotecarios"
    assert datos["coberturas"] == [
        {
            "cobertura_id": str(COBERTURA_ID),
            "codigo": "FALLECIMIENTO",
            "nombre": "Fallecimiento del asegurado",
            "limite_asegurado": "200000000.00",
            "deducible": "0.00",
            "prima": "1416100.00",
        }
    ]
    assert datos["prima"]["impuestos"] == [{"concepto": "IVA", "tasa": "0.19", "valor": "226100.00"}]
    assert datos["prima"]["total"] == "1416100.00"
    assert datos["condiciones"]["version_generales"] == "1.0"
    assert datos["condiciones"]["aceptadas_en"] == "2026-11-12T19:00:00+00:00"
    assert "vigencia_propuesta" in datos["condiciones"]["particulares"]


async def test_vincula_la_firma_y_deja_el_evento_poliza_emitida_en_el_outbox():
    e = Escenario()

    resultado = await e.emitir()

    assert e.firma.estado == EstadoFirma.VINCULADA
    assert e.firma.poliza_id == resultado.poliza.poliza_id
    (evento,) = e.eventos.eventos
    assert evento.tipo == "PolizaEmitida" and evento.agregado_id == resultado.poliza.poliza_id
    mensaje = PolizaEmitida.desde_payload(evento.payload)
    assert mensaje.poliza_id == resultado.poliza.poliza_id
    assert (mensaje.cliente_id, mensaje.cotizacion_id) == (CLIENTE_ID, COTIZACION_ID)
    assert mensaje.numero == "POL-20261113-AAAA0001" and mensaje.correlation_id == "corr-1"
    assert evento.payload["evento_id"] == str(evento.evento_id)
    assert evento.payload["datos"]["prima_total"] == "1416100.00"
    assert evento.payload["datos"]["moneda"] == "COP"
    assert evento.payload["datos"]["producto_id"] == str(PRODUCTO_ID)


async def test_propaga_el_correlation_id_a_los_servicios():
    e = Escenario()

    await e.emitir()

    assert {correlacion for _, correlacion in e.cotizaciones.llamadas} == {"corr-1"}
    assert [nombre for nombre, _ in e.cotizaciones.llamadas] == ["cotizacion", "producto", "condiciones"]


async def test_un_mensaje_duplicado_devuelve_la_poliza_existente_sin_emitir_otra():
    e = Escenario()
    primera = await e.emitir()
    e.cotizaciones.llamadas.clear()

    repetida = await e.emitir()

    assert repetida.creada is False
    assert repetida.poliza.poliza_id == primera.poliza.poliza_id
    assert len(e.polizas.polizas) == 1 and len(e.eventos.eventos) == 1
    assert e.cotizaciones.llamadas == []


async def test_carrera_entre_entregas_simultaneas_devuelve_la_poliza_ganadora():
    e = Escenario()
    ganadora = await Escenario().emitir()
    consultas = []
    original = e.polizas.obtener_por_cotizacion

    async def aparece_despues(cotizacion_id):
        consultas.append(1)
        if len(consultas) == 1:
            return None
        return ganadora.poliza

    async def guardar_duplicada(poliza):
        raise PolizaDuplicadaError()

    e.polizas.obtener_por_cotizacion = aparece_despues
    e.polizas.guardar = guardar_duplicada
    assert original is not None

    resultado = await e.emitir()

    assert resultado.creada is False and resultado.poliza is ganadora.poliza
    assert e.tx.rollbacks == 1 and e.tx.commits == 0 and e.eventos.eventos == []


async def test_duplicado_sin_poliza_existente_relanza_el_error():
    e = Escenario()

    async def guardar_duplicada(poliza):
        raise PolizaDuplicadaError()

    e.polizas.guardar = guardar_duplicada

    with pytest.raises(PolizaDuplicadaError):
        await e.emitir()

    assert e.tx.rollbacks == 1


@pytest.mark.parametrize(
    "firma_ajena", [None, "otro_cliente"], ids=["sin_firma", "firma_de_otro_cliente"]
)
async def test_exige_firma_digital_del_cliente_que_pago(firma_ajena):
    e = Escenario(firma_vigente=firma_ajena is not None)
    if firma_ajena:
        e.firma.cliente_id = uuid.uuid4()

    with pytest.raises(FirmaRequeridaError):
        await e.emitir()

    assert e.polizas.polizas == {} and e.eventos.eventos == [] and e.cotizaciones.llamadas == []


async def test_una_firma_reemplazada_durante_la_emision_revierte_todo():
    e = Escenario()
    e.firmas.vincular_resultado = False

    with pytest.raises(FirmaRequeridaError):
        await e.emitir()

    assert e.tx.rollbacks == 1 and e.tx.commits == 0


@pytest.mark.parametrize(
    ("cambios_pago", "cambios_cotizacion"),
    [
        ({"monto": Decimal("1416099.99")}, {}),
        ({"monto": Decimal("1")}, {}),
        ({"moneda": "USD"}, {}),
        ({}, {"cliente_id": uuid.uuid4()}),
    ],
)
async def test_rechaza_un_pago_que_no_corresponde_a_la_cotizacion(cambios_pago, cambios_cotizacion):
    e = Escenario()
    e.cotizaciones.cotizacion = cotizacion(**cambios_cotizacion)
    pago = PagoAprobado(**{**PAGO.__dict__, **cambios_pago})

    with pytest.raises(PagoInconsistenteError):
        await e.emitir(pago)

    assert e.polizas.polizas == {} and e.eventos.eventos == []


async def test_tolera_la_diferencia_de_escala_en_el_monto():
    e = Escenario()
    pago = PagoAprobado(**{**PAGO.__dict__, "monto": Decimal("1416100")})

    assert (await e.emitir(pago)).creada is True


@pytest.mark.parametrize(
    "particulares",
    [
        {},
        {"vigencia_propuesta": None},
        {"vigencia_propuesta": {"desde": "2026-11-13T13:00:00+00:00"}},
        {"vigencia_propuesta": {"desde": "ayer", "hasta": "mañana"}},
        {"vigencia_propuesta": {"desde": "2026-11-13T13:00:00+00:00", "hasta": "2026-11-13T13:00:00+00:00"}},
        {"vigencia_propuesta": {"desde": "2027-01-01T00:00:00+00:00", "hasta": "2026-01-01T00:00:00+00:00"}},
    ],
)
async def test_exige_una_vigencia_valida_en_las_condiciones(particulares):
    e = Escenario()
    e.cotizaciones.condiciones = CondicionesEmision("1.0", particulares)

    with pytest.raises(DatosEmisionInvalidosError):
        await e.emitir()

    assert e.polizas.polizas == {}


async def test_la_vigencia_sin_zona_horaria_se_toma_como_utc():
    e = Escenario()
    e.cotizaciones.condiciones = CondicionesEmision(
        "1.0",
        {"vigencia_propuesta": {"desde": "2026-11-13T13:00:00", "hasta": "2027-11-13T13:00:00"}},
    )

    resultado = await e.emitir()

    assert resultado.poliza.vigencia_desde == datetime(2026, 11, 13, 13, tzinfo=UTC)
    assert resultado.poliza.vigencia_desde.tzinfo is not None


async def test_exige_coberturas():
    e = Escenario()
    e.cotizaciones.cotizacion = cotizacion(coberturas=())

    with pytest.raises(DatosEmisionInvalidosError):
        await e.emitir()


@pytest.mark.parametrize("origen", ["cotizacion", "titular"])
async def test_un_servicio_caido_no_emite_ni_deja_estado(origen):
    e = Escenario()
    error = ServicioNoDisponibleError(origen)
    if origen == "cotizacion":
        e.cotizaciones.error = error
    else:
        e.titulares.error = error

    with pytest.raises(ServicioNoDisponibleError):
        await e.emitir()

    assert e.polizas.polizas == {} and e.eventos.eventos == []
    assert e.firma.estado == EstadoFirma.CAPTURADA and e.tx.commits == 0


async def test_cotizacion_inexistente():
    e = Escenario()
    e.cotizaciones.cotizacion = cotizacion(cotizacion_id=uuid.uuid4())

    with pytest.raises(CotizacionNoEncontradaError):
        await e.emitir()


async def test_error_inesperado_al_persistir_revierte():
    e = Escenario()

    async def falla(contrato):
        raise RuntimeError("base de datos caída")

    e.polizas.guardar_contrato = falla

    with pytest.raises(RuntimeError):
        await e.emitir()

    assert e.tx.rollbacks == 1 and e.tx.commits == 0


def test_numero_de_poliza_tiene_fecha_y_sufijo_unico():
    primero = numero_de_poliza(AHORA)
    segundo = numero_de_poliza(AHORA)

    assert primero.startswith("POL-20261113-") and len(primero) == len("POL-20261113-AB12CD34")
    assert primero != segundo
