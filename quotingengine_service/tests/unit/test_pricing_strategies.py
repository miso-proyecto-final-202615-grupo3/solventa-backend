import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.application.ports.perfil_cliente_gateway import (
    ConsentimientoNoOtorgadoError,
    PerfilCliente,
    PerfilNoDisponibleError,
)
from src.application.ports.open_data_gateway import (
    OpenDataNoDisponibleError,
    PerfilTerritorial,
)
from src.application.pricing.registry import (
    EstrategiaNoRegistradaError,
    PricingStrategyRegistry,
)
from src.application.pricing.strategies.otros_productos import ViajePricingStrategy
from src.application.pricing.strategies.vida_hipotecario import (
    DEGRADACION_PERFIL_NO_DISPONIBLE,
    VidaHipotecarioPricingStrategy,
)
from src.application.pricing.strategy import ContextoPricing, SenalesPricing
from src.domain.productos.entities import ProductoSeguro
from src.domain.open_data import CategoriaOpenData
from src.domain.reglas_rating.entities import ReglaRating
from tests.fakes import FakePerfilGateway


def _contexto(senales: SenalesPricing | None = None) -> ContextoPricing:
    producto = ProductoSeguro(
        codigo="VIDA_HIPOTECARIO", nombre="Vida", ramo="VIDA", pais="CO"
    )
    regla = ReglaRating(
        producto_id=producto.producto_id,
        version="1.0",
        vigente_desde=datetime.now(timezone.utc),
        definicion={
            "moneda": "COP",
            "tasa_base": "0.00025",
            "iva": "0.19",
            "parametro_monto": "saldo_credito",
        },
    )
    return ContextoPricing(
        uuid.uuid4(),
        producto,
        regla,
        {
            "saldo_credito": Decimal("200000000"),
            "ubicacion": {"municipio": "Bogota", "zona": "URBANA", "estrato": 4},
        },
        senales or SenalesPricing(),
    )


def test_calculo_base_con_iva():
    resultado = VidaHipotecarioPricingStrategy(
        FakePerfilGateway(), FakeOpenDataGateway()
    ).calcular(_contexto())

    assert resultado.prima_base == Decimal("50000.00")
    assert resultado.ajustes == []
    assert resultado.prima_neta == Decimal("50000.00")
    assert resultado.impuestos[0].valor == Decimal("9500.00")
    assert resultado.prima_total == Decimal("59500.00")
    assert resultado.moneda == "COP"
    assert not resultado.degradado


def test_aplica_factores_open_finance_y_open_data():
    senales = SenalesPricing(
        perfil=PerfilCliente(
            cliente_id=uuid.uuid4(),
            nombres="Ana",
            apellidos="Pérez",
            tipo_documento="CC",
            numero_identificacion="123",
            correo="ana@example.com",
            fecha_nacimiento=None,
            pais_residencia="CO",
            telefono="3000000000",
            estado_kyc="VALIDADO",
            ingreso_mensual=Decimal("8500000"),
            ahorros_liquidos=Decimal("25500000"),
            dti_pct=Decimal("28"),
            sobregiros_12_meses=0,
            score=820,
        ),
        perfil_territorial=PerfilTerritorial(CategoriaOpenData.BAJO_RIESGO),
    )
    strategy = VidaHipotecarioPricingStrategy(
        FakePerfilGateway(), FakeOpenDataGateway()
    )

    resultado = strategy.calcular(_contexto(senales))

    assert resultado.prima_base == Decimal("50000.00")
    assert [(a.concepto, a.tipo.value, a.valor) for a in resultado.ajustes] == [
        ("OPEN_FINANCE", "DEDUCCION", Decimal("7500.00")),
        ("OPEN_DATA", "DEDUCCION", Decimal("2125.00")),
    ]
    assert resultado.prima_neta == Decimal("40375.00")
    assert resultado.prima_total == Decimal("48046.25")


def test_perfil_financiero_alto_riesgo_aplica_recargo():
    perfil = PerfilCliente(
        cliente_id=uuid.uuid4(),
        nombres="Ana",
        apellidos="Pérez",
        tipo_documento="CC",
        numero_identificacion="123",
        correo="ana@example.com",
        fecha_nacimiento=None,
        pais_residencia="CO",
        telefono="3000000000",
        estado_kyc="VALIDADO",
        dti_pct=Decimal("55"),
        ahorros_liquidos=Decimal("1000000"),
        ingreso_mensual=Decimal("8500000"),
        sobregiros_12_meses=3,
        score=550,
    )
    senales = SenalesPricing(
        perfil=perfil,
        perfil_territorial=PerfilTerritorial(CategoriaOpenData.ESTANDAR),
    )

    resultado = VidaHipotecarioPricingStrategy(
        FakePerfilGateway(), FakeOpenDataGateway()
    ).calcular(_contexto(senales))

    assert resultado.ajustes[0].tipo.value == "RECARGO"
    assert resultado.ajustes[0].valor == Decimal("10000.00")
    assert resultado.prima_total == Decimal("71400.00")


async def test_hipotecario_recolecta_perfil():
    gateway = FakePerfilGateway()
    cliente_id = uuid.uuid4()

    senales = await VidaHipotecarioPricingStrategy(
        gateway, FakeOpenDataGateway()
    ).recolectar_senales(cliente_id, _contexto().parametros)

    assert senales.perfil is not None
    assert senales.perfil.cliente_id == cliente_id
    assert senales.perfil_territorial.categoria == CategoriaOpenData.BAJO_RIESGO
    assert senales.degradaciones == ()


@pytest.mark.parametrize(
    ("error", "motivo"),
    [
        (PerfilNoDisponibleError(), DEGRADACION_PERFIL_NO_DISPONIBLE),
    ],
)
async def test_hipotecario_degrada_sin_perfil(error, motivo):
    estrategia = VidaHipotecarioPricingStrategy(
        FakePerfilGateway(error), FakeOpenDataGateway()
    )

    senales = await estrategia.recolectar_senales(
        uuid.uuid4(), _contexto().parametros
    )
    resultado = estrategia.calcular(_contexto(senales))

    assert senales.perfil is None
    assert resultado.degradaciones == (motivo,)
    assert resultado.degradado


async def test_open_finance_no_disponible_usa_factor_neutral():
    from dataclasses import replace

    class OpenFinanceNoDisponible:
        async def obtener_perfil(self, cliente_id):
            return replace(
                await FakePerfilGateway().obtener_perfil(cliente_id),
                open_finance_disponible=False,
                ingreso_mensual=None,
                ahorros_liquidos=None,
                dti_pct=None,
                sobregiros_12_meses=None,
                score=None,
            )

    senales = await VidaHipotecarioPricingStrategy(
        OpenFinanceNoDisponible(), FakeOpenDataGateway()
    ).recolectar_senales(uuid.uuid4(), _contexto().parametros)
    resultado = VidaHipotecarioPricingStrategy(
        FakePerfilGateway(), FakeOpenDataGateway()
    ).calcular(_contexto(senales))

    assert resultado.prima_total == Decimal("56525.00")
    assert "OPEN_FINANCE_NO_DISPONIBLE" in resultado.degradaciones


async def test_hipotecario_rechaza_sin_consentimiento():
    estrategia = VidaHipotecarioPricingStrategy(
        FakePerfilGateway(ConsentimientoNoOtorgadoError()), FakeOpenDataGateway()
    )

    with pytest.raises(ConsentimientoNoOtorgadoError):
        await estrategia.recolectar_senales(uuid.uuid4(), _contexto().parametros)


class FakeOpenDataGateway:
    async def obtener_riesgo(self, ubicacion):
        return PerfilTerritorial(CategoriaOpenData.BAJO_RIESGO)


async def test_open_data_indisponible_degrada_con_factor_neutral():
    class OpenDataNoDisponible:
        async def obtener_riesgo(self, ubicacion):
            raise OpenDataNoDisponibleError

    estrategia = VidaHipotecarioPricingStrategy(
        FakePerfilGateway(), OpenDataNoDisponible()
    )

    senales = await estrategia.recolectar_senales(
        uuid.uuid4(), _contexto().parametros
    )
    resultado = estrategia.calcular(_contexto(senales))

    assert senales.perfil_territorial.categoria == CategoriaOpenData.ESTANDAR
    assert "OPEN_DATA_NO_DISPONIBLE" in resultado.degradaciones


async def test_estrategia_por_defecto_no_consulta_perfil():
    senales = await ViajePricingStrategy().recolectar_senales(uuid.uuid4())

    assert senales == SenalesPricing()


def test_registry_resuelve_por_codigo():
    estrategia = ViajePricingStrategy()
    registry = PricingStrategyRegistry([estrategia])

    assert registry.obtener("SEGURO_VIAJE") is estrategia
    with pytest.raises(EstrategiaNoRegistradaError):
        registry.obtener("OTRO")
