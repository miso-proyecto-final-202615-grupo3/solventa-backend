import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.application.ports.perfil_cliente_gateway import (
    ConsentimientoNoOtorgadoError,
    PerfilNoDisponibleError,
)
from src.application.pricing.registry import (
    EstrategiaNoRegistradaError,
    PricingStrategyRegistry,
)
from src.application.pricing.strategies.otros_productos import ViajePricingStrategy
from src.application.pricing.strategies.vida_hipotecario import (
    DEGRADACION_PERFIL_NO_DISPONIBLE,
    DEGRADACION_SIN_CONSENTIMIENTO,
    VidaHipotecarioPricingStrategy,
)
from src.application.pricing.strategy import ContextoPricing, SenalesPricing
from src.domain.productos.entities import ProductoSeguro
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
            "parametro_monto": "valor_vivienda",
        },
    )
    return ContextoPricing(
        uuid.uuid4(),
        producto,
        regla,
        {"valor_vivienda": Decimal("200000000")},
        senales or SenalesPricing(),
    )


def test_calculo_base_con_iva():
    resultado = VidaHipotecarioPricingStrategy(FakePerfilGateway()).calcular(
        _contexto()
    )

    assert resultado.prima_base == Decimal("50000.00")
    assert resultado.ajustes == []
    assert resultado.prima_neta == Decimal("50000.00")
    assert resultado.impuestos[0].valor == Decimal("9500.00")
    assert resultado.prima_total == Decimal("59500.00")
    assert resultado.moneda == "COP"
    assert not resultado.degradado


async def test_hipotecario_recolecta_perfil():
    gateway = FakePerfilGateway()
    cliente_id = uuid.uuid4()

    senales = await VidaHipotecarioPricingStrategy(gateway).recolectar_senales(
        cliente_id
    )

    assert senales.perfil is not None
    assert senales.perfil.cliente_id == cliente_id
    assert senales.degradaciones == ()


@pytest.mark.parametrize(
    ("error", "motivo"),
    [
        (ConsentimientoNoOtorgadoError(), DEGRADACION_SIN_CONSENTIMIENTO),
        (PerfilNoDisponibleError(), DEGRADACION_PERFIL_NO_DISPONIBLE),
    ],
)
async def test_hipotecario_degrada_sin_perfil(error, motivo):
    estrategia = VidaHipotecarioPricingStrategy(FakePerfilGateway(error))

    senales = await estrategia.recolectar_senales(uuid.uuid4())
    resultado = estrategia.calcular(_contexto(senales))

    assert senales.perfil is None
    assert resultado.degradaciones == (motivo,)
    assert resultado.degradado


async def test_estrategia_por_defecto_no_consulta_perfil():
    senales = await ViajePricingStrategy().recolectar_senales(uuid.uuid4())

    assert senales == SenalesPricing()


def test_registry_resuelve_por_codigo():
    estrategia = ViajePricingStrategy()
    registry = PricingStrategyRegistry([estrategia])

    assert registry.obtener("SEGURO_VIAJE") is estrategia
    with pytest.raises(EstrategiaNoRegistradaError):
        registry.obtener("OTRO")
