from calendar import isleap
from datetime import datetime, timezone

_PRODUCTOS_DIEZ_ANOS = frozenset({
    "VIDA_HIPOTECARIO",
    "PROTECCION_PAGOS",
    "MICROSEGURO_VIDA",
})


def calcular_vigencia_propuesta(
    creada_en: datetime, producto_codigo: str
) -> tuple[datetime, datetime]:
    inicio = creada_en if creada_en.tzinfo is not None else creada_en.replace(tzinfo=timezone.utc)
    anos = 10 if producto_codigo in _PRODUCTOS_DIEZ_ANOS else 1
    ano_fin = inicio.year + anos
    dia_fin = (
        28 if inicio.month == 2 and inicio.day == 29 and not isleap(ano_fin)
        else inicio.day
    )
    return inicio, inicio.replace(year=ano_fin, day=dia_fin)
