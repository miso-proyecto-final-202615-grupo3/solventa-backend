import pytest

from src.infrastructure.pdf.formatos import (
    SIN_DATO,
    formato_fecha,
    formato_moneda,
    formato_numero,
    formato_porcentaje,
)


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("1250000.5", "1.250.000,50"),
        (1250000.505, "1.250.000,51"),
        ("0", "0,00"),
        ("999.999", "1.000,00"),
        ("-1234.5", "-1.234,50"),
        ("200000000", "200.000.000,00"),
        (None, SIN_DATO),
        ("abc", SIN_DATO),
        ("NaN", SIN_DATO),
    ],
)
def test_formato_numero_es_co(valor, esperado):
    assert formato_numero(valor) == esperado


def test_formato_numero_sin_decimales():
    assert formato_numero("1234567.89", 0) == "1.234.568"


def test_formato_moneda_usa_espacio_fijo_entre_moneda_e_importe():
    assert formato_moneda("1416100", "COP") == "COP\u00a01.416.100,00"
    assert formato_moneda("10", None) == "10,00"
    assert formato_moneda(None, "COP") == SIN_DATO


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [("0.19", "19,00\u00a0%"), ("0.075", "7,50\u00a0%"), ("1", "100,00\u00a0%"), (None, SIN_DATO)],
)
def test_formato_porcentaje(valor, esperado):
    assert formato_porcentaje(valor) == esperado


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("2026-11-13", "13 de noviembre de 2026"),
        ("2036-01-01", "1 de enero de 2036"),
        ("2026-12-31", "31 de diciembre de 2026"),
        ("no-es-fecha", SIN_DATO),
        (None, SIN_DATO),
    ],
)
def test_formato_fecha_en_espanol_sin_hora(valor, esperado):
    assert formato_fecha(valor) == esperado
