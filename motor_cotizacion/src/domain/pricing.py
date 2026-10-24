from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum


class CategoriaOpenFinance(StrEnum):
    A = "A"
    B = "B"
    C = "C"


@dataclass(frozen=True)
class PerfilFinanciero:
    ingreso_mensual: Decimal | None
    ahorros_liquidos: Decimal | None
    dti_pct: Decimal | None
    sobregiros_12_meses: int | None
    score: int | None


@dataclass(frozen=True)
class ResultadoPricing:
    categoria_open_finance: CategoriaOpenFinance
    factor_open_finance: Decimal
    prima_base: Decimal
    ajuste_open_finance: Decimal
    ajuste_open_data: Decimal
    prima_neta: Decimal
    impuestos: Decimal
    prima_total: Decimal


TASA_BASE_MENSUAL = Decimal("0.00025")
IVA = Decimal("0.19")
FACTORES_OPEN_DATA = {
    Decimal("0.95"),
    Decimal("1.00"),
    Decimal("1.10"),
}
FACTORES_OPEN_FINANCE = {
    CategoriaOpenFinance.A: Decimal("0.85"),
    CategoriaOpenFinance.B: Decimal("1.00"),
    CategoriaOpenFinance.C: Decimal("1.20"),
}
CENTAVO = Decimal("0.01")


def clasificar_open_finance(
    perfil: PerfilFinanciero,
) -> CategoriaOpenFinance:
    if (
        (perfil.dti_pct is not None and perfil.dti_pct > 50)
        or (perfil.score is not None and perfil.score < 600)
        or (
            perfil.sobregiros_12_meses is not None
            and perfil.sobregiros_12_meses >= 3
        )
    ):
        return CategoriaOpenFinance.C

    reserva_suficiente = (
        perfil.ingreso_mensual is not None
        and perfil.ingreso_mensual > 0
        and perfil.ahorros_liquidos is not None
        and perfil.ahorros_liquidos >= perfil.ingreso_mensual * 3
    )
    perfil_excelente = (
        perfil.dti_pct is not None
        and perfil.dti_pct <= 30
        and perfil.score is not None
        and perfil.score >= 800
        and perfil.sobregiros_12_meses == 0
        and reserva_suficiente
    )
    if perfil_excelente:
        return CategoriaOpenFinance.A
    return CategoriaOpenFinance.B


def calcular_pricing(
    saldo_credito: Decimal,
    perfil: PerfilFinanciero,
    factor_open_data: Decimal,
) -> ResultadoPricing:
    if saldo_credito <= 0:
        raise ValueError("El saldo del crédito debe ser mayor que cero.")
    if factor_open_data not in FACTORES_OPEN_DATA:
        raise ValueError("El factor Open Data no está configurado.")

    categoria = clasificar_open_finance(perfil)
    factor_open_finance = FACTORES_OPEN_FINANCE[categoria]
    prima_base = _dinero(saldo_credito * TASA_BASE_MENSUAL)
    ajuste_open_finance = _dinero(
        prima_base * (factor_open_finance - Decimal("1.00"))
    )
    prima_tras_open_finance = prima_base * factor_open_finance
    ajuste_open_data = _dinero(
        prima_tras_open_finance * (factor_open_data - Decimal("1.00"))
    )
    prima_neta = _dinero(prima_base + ajuste_open_finance + ajuste_open_data)
    impuestos = _dinero(prima_neta * IVA)

    return ResultadoPricing(
        categoria_open_finance=categoria,
        factor_open_finance=factor_open_finance,
        prima_base=prima_base,
        ajuste_open_finance=ajuste_open_finance,
        ajuste_open_data=ajuste_open_data,
        prima_neta=prima_neta,
        impuestos=impuestos,
        prima_total=_dinero(prima_neta + impuestos),
    )


def _dinero(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)
