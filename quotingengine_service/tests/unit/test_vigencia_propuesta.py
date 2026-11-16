from datetime import datetime, timezone

import pytest

from src.domain.cotizaciones.vigencia_propuesta import calcular_vigencia_propuesta


@pytest.mark.parametrize(
    ("producto", "anos"),
    [
        ("VIDA_HIPOTECARIO", 10),
        ("PROTECCION_PAGOS", 10),
        ("MICROSEGURO_VIDA", 10),
        ("SEGURO_VIAJE", 1),
        ("PROTECCION_DISPOSITIVOS", 1),
        ("SEGURO_PARAMETRICO", 1),
    ],
)
def test_vigencia_por_producto(producto, anos):
    inicio = datetime(2026, 11, 7, 12, 34, 56, tzinfo=timezone.utc)
    desde, hasta = calcular_vigencia_propuesta(inicio, producto)
    assert desde == inicio
    assert hasta == inicio.replace(year=inicio.year + anos)


@pytest.mark.parametrize(
    ("inicio", "producto", "fin"),
    [
        (datetime(2024, 2, 29, 10, tzinfo=timezone.utc), "SEGURO_VIAJE", datetime(2025, 2, 28, 10, tzinfo=timezone.utc)),
        (datetime(2024, 2, 29, 10, tzinfo=timezone.utc), "VIDA_HIPOTECARIO", datetime(2034, 2, 28, 10, tzinfo=timezone.utc)),
        (datetime(2088, 2, 29, 10, tzinfo=timezone.utc), "SEGURO_VIAJE", datetime(2089, 2, 28, 10, tzinfo=timezone.utc)),
        (datetime(2024, 2, 28, 10, tzinfo=timezone.utc), "MICROSEGURO_VIDA", datetime(2034, 2, 28, 10, tzinfo=timezone.utc)),
    ],
)
def test_vigencia_fechas_limite(inicio, producto, fin):
    assert calcular_vigencia_propuesta(inicio, producto) == (inicio, fin)


def test_fecha_sin_zona_se_interpreta_como_utc():
    desde, hasta = calcular_vigencia_propuesta(
        datetime(2026, 1, 1, 10), "SEGURO_VIAJE"
    )
    assert desde == datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
    assert hasta == datetime(2027, 1, 1, 10, tzinfo=timezone.utc)
