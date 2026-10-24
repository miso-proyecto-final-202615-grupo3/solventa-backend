from decimal import Decimal

import pytest

from src.domain.pricing import (
    CategoriaOpenFinance,
    PerfilFinanciero,
    calcular_pricing,
    clasificar_open_finance,
)


@pytest.mark.parametrize(
    ("perfil", "categoria"),
    [
        (
            PerfilFinanciero(
                ingreso_mensual=Decimal("8500000"),
                ahorros_liquidos=Decimal("25500000"),
                dti_pct=Decimal("30"),
                sobregiros_12_meses=0,
                score=800,
            ),
            CategoriaOpenFinance.A,
        ),
        (
            PerfilFinanciero(
                ingreso_mensual=Decimal("8500000"),
                ahorros_liquidos=Decimal("25500000"),
                dti_pct=Decimal("28"),
                sobregiros_12_meses=0,
                score=820,
            ),
            CategoriaOpenFinance.A,
        ),
        (
            PerfilFinanciero(
                ingreso_mensual=Decimal("8500000"),
                ahorros_liquidos=Decimal("25499999"),
                dti_pct=Decimal("28"),
                sobregiros_12_meses=0,
                score=820,
            ),
            CategoriaOpenFinance.B,
        ),
        (
            PerfilFinanciero(
                ingreso_mensual=Decimal("8500000"),
                ahorros_liquidos=Decimal("50000000"),
                dti_pct=Decimal("50"),
                sobregiros_12_meses=0,
                score=700,
            ),
            CategoriaOpenFinance.B,
        ),
        (
            PerfilFinanciero(
                ingreso_mensual=Decimal("8500000"),
                ahorros_liquidos=Decimal("50000000"),
                dti_pct=Decimal("50.01"),
                sobregiros_12_meses=0,
                score=820,
            ),
            CategoriaOpenFinance.C,
        ),
        (
            PerfilFinanciero(
                ingreso_mensual=Decimal("8500000"),
                ahorros_liquidos=Decimal("50000000"),
                dti_pct=Decimal("20"),
                sobregiros_12_meses=3,
                score=820,
            ),
            CategoriaOpenFinance.C,
        ),
        (
            PerfilFinanciero(
                ingreso_mensual=None,
                ahorros_liquidos=Decimal("50000000"),
                dti_pct=Decimal("20"),
                sobregiros_12_meses=0,
                score=820,
            ),
            CategoriaOpenFinance.B,
        ),
    ],
)
def test_clasifica_perfil_financiero(perfil, categoria):
    assert clasificar_open_finance(perfil) == categoria


def test_calcula_prima_y_desglose_del_ejemplo_hu_1_2_4():
    perfil = PerfilFinanciero(
        ingreso_mensual=Decimal("8500000"),
        ahorros_liquidos=Decimal("25500000"),
        dti_pct=Decimal("28"),
        sobregiros_12_meses=0,
        score=820,
    )

    resultado = calcular_pricing(
        saldo_credito=Decimal("200000000"),
        perfil=perfil,
        factor_open_data=Decimal("0.95"),
    )

    assert resultado.categoria_open_finance == CategoriaOpenFinance.A
    assert resultado.prima_base == Decimal("50000.00")
    assert resultado.ajuste_open_finance == Decimal("-7500.00")
    assert resultado.ajuste_open_data == Decimal("-2125.00")
    assert resultado.prima_neta == Decimal("40375.00")
    assert resultado.impuestos == Decimal("7671.25")
    assert resultado.prima_total == Decimal("48046.25")


@pytest.mark.parametrize("saldo", [Decimal("0"), Decimal("-1")])
def test_rechaza_saldo_hipotecario_no_positivo(saldo):
    perfil = PerfilFinanciero(
        ingreso_mensual=Decimal("8500000"),
        ahorros_liquidos=Decimal("25500000"),
        dti_pct=Decimal("28"),
        sobregiros_12_meses=0,
        score=820,
    )

    with pytest.raises(ValueError, match="saldo del crédito"):
        calcular_pricing(
            saldo_credito=saldo,
            perfil=perfil,
            factor_open_data=Decimal("1.00"),
        )


@pytest.mark.parametrize("factor", [Decimal("0.90"), Decimal("1.05")])
def test_rechaza_factor_open_data_no_configurado(factor):
    perfil = PerfilFinanciero(
        ingreso_mensual=Decimal("8500000"),
        ahorros_liquidos=Decimal("25500000"),
        dti_pct=Decimal("28"),
        sobregiros_12_meses=0,
        score=820,
    )

    with pytest.raises(ValueError, match="factor Open Data"):
        calcular_pricing(
            saldo_credito=Decimal("200000000"),
            perfil=perfil,
            factor_open_data=factor,
        )
