"""HU4.2.3 · Reglas paramétricas (Strategy): normalización del evento y evaluación del umbral por póliza."""
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.domain.siniestros.parametricos import (
    CoberturaParametrica,
    EventoNoProcesable,
    PolizaParametrica,
    cobertura_id,
    normalizar_indice,
    regla_para,
)

OCURRIDO = datetime(2026, 11, 21, 20, 0, tzinfo=UTC)


def _suscripcion(cobertura: str, indice: str, umbral: str) -> PolizaParametrica:
    return PolizaParametrica(
        poliza_id=uuid.uuid4(), cliente_id=uuid.uuid4(), poliza_numero="SLV-1", cobertura=cobertura, indice=indice,
        umbral=Decimal(umbral), monto_compensacion=Decimal("300000"), moneda="COP", actualizada_en=OCURRIDO,
    )


def test_lluvia_se_normaliza_y_activa_desde_el_umbral():
    regla = regla_para("LLUVIA")
    evento = regla.normalizar({"zona": " bogota ", "precipitacion_mm": 72.5}, OCURRIDO)

    assert (evento.cobertura, evento.indice, evento.valor) == (CoberturaParametrica.LLUVIA_EXTREMA, "BOGOTA", Decimal("72.5"))
    assert regla.cumple(evento, _suscripcion("LLUVIA_EXTREMA", "BOGOTA", "50"))
    assert regla.cumple(evento, _suscripcion("LLUVIA_EXTREMA", "BOGOTA", "72.5"))  # igual al umbral activa
    assert not regla.cumple(evento, _suscripcion("LLUVIA_EXTREMA", "BOGOTA", "80"))
    assert not regla.cumple(evento, _suscripcion("LLUVIA_EXTREMA", "MEDELLIN", "10"))
    assert "72.5 mm en BOGOTA" in regla.resumen(evento, _suscripcion("LLUVIA_EXTREMA", "BOGOTA", "50"))


def test_retraso_de_vuelo():
    regla = regla_para("RETRASO_VUELO")
    evento = regla.normalizar({"vuelo": "av 9450", "retraso_minutos": 185}, OCURRIDO)

    assert (evento.cobertura, evento.indice) == (CoberturaParametrica.RETRASO_VUELO, "AV9450")
    assert regla.cumple(evento, _suscripcion("RETRASO_VUELO", "AV9450", "120"))
    assert not regla.cumple(evento, _suscripcion("RETRASO_VUELO", "AV9450", "200"))
    assert regla.describir(evento, _suscripcion("RETRASO_VUELO", "AV9450", "120")).startswith("RETRASO_VUELO: retraso_minutos=185")


@pytest.mark.parametrize(
    ("tipo", "datos"),
    [
        ("LLUVIA", {"precipitacion_mm": 10}),
        ("LLUVIA", {"zona": "BOGOTA"}),
        ("LLUVIA", {"zona": "BOGOTA", "precipitacion_mm": -1}),
        ("LLUVIA", {"zona": "BOGOTA", "precipitacion_mm": "mucha"}),
        ("LLUVIA", {"zona": "BOGOTA", "precipitacion_mm": True}),
        ("LLUVIA", {"zona": "  ", "precipitacion_mm": 10}),
        ("RETRASO_VUELO", {"vuelo": "AV1"}),
        ("GRANIZO", {"zona": "BOGOTA"}),
    ],
)
def test_eventos_que_no_se_pueden_interpretar(tipo, datos):
    with pytest.raises(EventoNoProcesable):
        regla_para(tipo).normalizar(datos, OCURRIDO)


def test_indice_y_cobertura_estables():
    assert normalizar_indice(" Av 9450 ") == "AV9450"
    assert cobertura_id("LLUVIA_EXTREMA") == cobertura_id("LLUVIA_EXTREMA") != cobertura_id("RETRASO_VUELO")
