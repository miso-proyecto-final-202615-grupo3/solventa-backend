"""Formatos de presentación (es-CO) que usa la plantilla del certificado."""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

SIN_DATO = "—"
_MESES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)
_ESPACIO_FIJO = "\u00a0"


def _decimal(valor: Any) -> Decimal | None:
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return None
    return numero if numero.is_finite() else None


def formato_numero(valor: Any, decimales: int = 2) -> str:
    """1250000.5 -> '1.250.000,50' (punto de miles, coma decimal)."""
    numero = _decimal(valor)
    if numero is None:
        return SIN_DATO
    cuantizado = numero.quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)
    entero, _, fraccion = f"{abs(cuantizado):f}".partition(".")
    entero = f"{int(entero):,}".replace(",", ".")
    signo = "-" if cuantizado < 0 else ""
    return f"{signo}{entero},{fraccion}" if decimales else f"{signo}{entero}"


def formato_moneda(valor: Any, moneda: str | None) -> str:
    """1250000.5, 'COP' -> 'COP 1.250.000,50'."""
    numero = formato_numero(valor)
    if numero == SIN_DATO:
        return SIN_DATO
    return f"{moneda}{_ESPACIO_FIJO}{numero}" if moneda else numero


def formato_porcentaje(fraccion: Any) -> str:
    """0.19 -> '19,00 %'."""
    numero = _decimal(fraccion)
    if numero is None:
        return SIN_DATO
    return f"{formato_numero(numero * 100)}{_ESPACIO_FIJO}%"


def formato_fecha(valor: Any) -> str:
    """'2026-11-13' -> '13 de noviembre de 2026'."""
    try:
        fecha = date.fromisoformat(str(valor))
    except ValueError:
        return SIN_DATO
    return f"{fecha.day} de {_MESES[fecha.month - 1]} de {fecha.year}"
