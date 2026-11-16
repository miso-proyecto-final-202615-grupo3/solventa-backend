import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.domain.eventos.mensajes import (
    MensajeInvalidoError,
    PagoAprobado,
    PolizaEmitida,
    payload_poliza_emitida,
)

PAGO_ID = "0f5d2a4e-3a54-4b0e-9a3b-8d6e2f1c7a10"
COTIZACION_ID = "95b19edf-6c4b-4437-99db-d84d0ef482fc"
CLIENTE_ID = "d0af9a19-872e-4e16-bc56-e8217d4ff024"


def pago_aprobado(**cambios) -> dict:
    """Mensaje exactamente como lo publica payments_service."""
    mensaje = {
        "evento_id": "7b3b1ab2-8cc6-4ea6-93bb-1d7d9c2c5f10",
        "tipo": "PagoAprobado",
        "version": 1,
        "ocurrido_en": "2026-11-13T14:00:00+00:00",
        "correlation_id": "corr-1",
        "datos": {
            "pago_id": PAGO_ID,
            "cotizacion_id": COTIZACION_ID,
            "cliente_id": CLIENTE_ID,
            "monto": "1250000.51",
            "moneda": "COP",
            "metodo_pago": "PAYPAL",
            "proveedor_referencia": "PAYPAL_1",
        },
    }
    if "datos" in cambios and cambios["datos"] is None:
        return {**mensaje, "datos": None, **{k: v for k, v in cambios.items() if k != "datos"}}
    datos = cambios.pop("datos", {})
    mensaje["datos"] = {**mensaje["datos"], **datos}
    return {**mensaje, **cambios}


def test_lee_el_mensaje_pago_aprobado_de_payments():
    pago = PagoAprobado.desde_payload(pago_aprobado())

    assert pago.pago_id == uuid.UUID(PAGO_ID)
    assert pago.cotizacion_id == uuid.UUID(COTIZACION_ID)
    assert pago.cliente_id == uuid.UUID(CLIENTE_ID)
    assert pago.monto == Decimal("1250000.51") and pago.moneda == "COP"
    assert pago.metodo_pago == "PAYPAL" and pago.proveedor_referencia == "PAYPAL_1"
    assert pago.correlation_id == "corr-1"
    assert pago.evento_id == "7b3b1ab2-8cc6-4ea6-93bb-1d7d9c2c5f10"


def test_correlation_id_y_referencia_son_opcionales():
    mensaje = pago_aprobado(correlation_id=None, datos={"proveedor_referencia": None})

    pago = PagoAprobado.desde_payload(mensaje)

    assert pago.correlation_id is None and pago.proveedor_referencia is None


@pytest.mark.parametrize(
    "mensaje",
    [
        None,
        [],
        "texto",
        pago_aprobado(tipo="PolizaEmitida"),
        pago_aprobado(version=2),
        pago_aprobado(version=None),
        pago_aprobado(datos=None),
        pago_aprobado(datos={"pago_id": "no-es-uuid"}),
        pago_aprobado(datos={"cotizacion_id": None}),
        pago_aprobado(datos={"cliente_id": 12}),
        pago_aprobado(datos={"monto": "abc"}),
        pago_aprobado(datos={"monto": "0"}),
        pago_aprobado(datos={"monto": "-5"}),
        pago_aprobado(datos={"monto": "NaN"}),
        pago_aprobado(datos={"monto": None}),
        pago_aprobado(datos={"moneda": "COPP"}),
        pago_aprobado(datos={"moneda": None}),
    ],
)
def test_rechaza_mensajes_que_incumplen_el_contrato(mensaje):
    with pytest.raises(MensajeInvalidoError):
        PagoAprobado.desde_payload(mensaje)


def test_falta_de_campo_obligatorio():
    mensaje = pago_aprobado()
    del mensaje["datos"]["monto"]

    with pytest.raises(MensajeInvalidoError):
        PagoAprobado.desde_payload(mensaje)


def test_poliza_emitida_ida_y_vuelta():
    evento_id, poliza_id = uuid.uuid4(), uuid.uuid4()
    cliente_id, cotizacion_id, producto_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    desde = datetime(2026, 11, 13, 13, tzinfo=UTC)

    payload = payload_poliza_emitida(
        evento_id,
        desde,
        "corr-9",
        poliza_id=poliza_id,
        cliente_id=cliente_id,
        cotizacion_id=cotizacion_id,
        producto_id=producto_id,
        numero="POL-1",
        vigencia_desde=desde,
        vigencia_hasta=datetime(2027, 11, 13, 13, tzinfo=UTC),
        prima_total=Decimal("1416100.00"),
        moneda="COP",
    )

    assert payload["tipo"] == "PolizaEmitida" and payload["version"] == 1
    assert payload["datos"]["prima_total"] == "1416100.00"
    assert payload["datos"]["vigencia_hasta"] == "2027-11-13T13:00:00+00:00"
    evento = PolizaEmitida.desde_payload(payload)
    assert (evento.poliza_id, evento.cliente_id, evento.cotizacion_id) == (
        poliza_id,
        cliente_id,
        cotizacion_id,
    )
    assert (evento.numero, evento.correlation_id, evento.evento_id) == (
        "POL-1",
        "corr-9",
        str(evento_id),
    )


@pytest.mark.parametrize(
    "mensaje",
    [
        pago_aprobado(),  # otro tipo de mensaje
        {"tipo": "PolizaEmitida", "version": 1, "datos": {"poliza_id": "x"}},
        {"tipo": "PolizaEmitida", "version": 1},
    ],
)
def test_poliza_emitida_rechaza_mensajes_invalidos(mensaje):
    with pytest.raises(MensajeInvalidoError):
        PolizaEmitida.desde_payload(mensaje)
