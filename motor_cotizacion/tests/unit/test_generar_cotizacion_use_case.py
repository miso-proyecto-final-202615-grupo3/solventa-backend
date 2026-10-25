import uuid
from decimal import Decimal

import pytest

from src.application.ports.perfilamiento import (
    CategoriaOpenData,
    ClienteCotizacionNoEncontradoError,
    ConsentimientoNoActivoError,
    OpenDataNoDisponibleError,
    OpenFinanceNoDisponibleError,
    PerfilTerritorial,
)
from src.application.use_cases.generar_cotizacion_use_case import (
    CotizarCommand,
    FuentePerfil,
    GenerarCotizacionUseCase,
)
from src.domain.pricing import PerfilFinanciero


CLIENTE_ID = uuid.uuid4()
PERFIL_A = PerfilFinanciero(
    ingreso_mensual=Decimal("8500000"),
    ahorros_liquidos=Decimal("25500000"),
    dti_pct=Decimal("28"),
    sobregiros_12_meses=0,
    score=820,
)
UBICACION = {"municipio": "Bogota", "zona": "URBANA", "estrato": 4}


class FakePerfilFinancieroProvider:
    def __init__(self, resultado=PERFIL_A):
        self.resultado = resultado
        self.llamadas = 0

    async def obtener_perfil_financiero(self, cliente_id):
        self.llamadas += 1
        if isinstance(self.resultado, Exception):
            raise self.resultado
        return self.resultado


class FakeOpenDataProvider:
    def __init__(self, resultado=None):
        self.resultado = resultado or PerfilTerritorial(
            categoria=CategoriaOpenData.BAJO_RIESGO,
            id_territorial=Decimal("0.95"),
            ir_publico=Decimal("1.00"),
        )
        self.error: Exception | None = None
        self.llamadas = 0

    async def obtener_riesgo_territorial(self, ubicacion):
        self.llamadas += 1
        assert ubicacion == UBICACION
        if self.error:
            raise self.error
        return self.resultado


class FakeOpenDataCache:
    def __init__(self, categoria=None, falla=False):
        self.categoria = categoria
        self.falla = falla
        self.guardados = []

    async def obtener(self, ubicacion):
        if self.falla:
            raise RuntimeError("Redis no disponible")
        return self.categoria

    async def guardar(self, ubicacion, perfil):
        if self.falla:
            raise RuntimeError("Redis no disponible")
        self.guardados.append((ubicacion, perfil))


def crear_comando():
    return CotizarCommand(
        cliente_id=CLIENTE_ID,
        saldo_credito=Decimal("200000000"),
        ubicacion=UBICACION,
    )


def crear_use_case(
    perfil=PERFIL_A,
    open_data=None,
    cache=None,
):
    perfil_provider = FakePerfilFinancieroProvider(perfil)
    open_data_provider = open_data or FakeOpenDataProvider()
    open_data_cache = cache or FakeOpenDataCache()
    use_case = GenerarCotizacionUseCase(
        perfil_provider,
        open_data_provider,
        open_data_cache,
    )
    return use_case, perfil_provider, open_data_provider, open_data_cache


async def test_genera_cotizacion_con_datos_de_proveedores():
    use_case, _, _, cache = crear_use_case()

    resultado = await use_case.ejecutar(crear_comando())

    assert resultado.pricing.prima_total == Decimal("48046.25")
    assert resultado.fuente_perfil == FuentePerfil.PROVEEDORES
    assert len(cache.guardados) == 1


async def test_falla_open_finance_continua_con_factor_neutral():
    use_case, _, _, _ = crear_use_case(
        perfil=OpenFinanceNoDisponibleError()
    )

    resultado = await use_case.ejecutar(crear_comando())

    assert resultado.pricing.factor_open_finance == Decimal("1.00")
    assert resultado.pricing.categoria_open_finance == "B"
    assert resultado.fuente_perfil == FuentePerfil.PARCIAL


async def test_falla_open_data_usa_ultimo_valor_en_cache():
    provider = FakeOpenDataProvider()
    provider.error = OpenDataNoDisponibleError()
    use_case, _, _, _ = crear_use_case(
        open_data=provider,
        cache=FakeOpenDataCache(CategoriaOpenData.RIESGO_ELEVADO),
    )

    resultado = await use_case.ejecutar(crear_comando())

    assert resultado.pricing.ajuste_open_data == Decimal("4250.00")
    assert resultado.fuente_perfil == FuentePerfil.PARCIAL


async def test_falla_open_data_sin_cache_usa_factor_estandar():
    provider = FakeOpenDataProvider()
    provider.error = OpenDataNoDisponibleError()
    use_case, _, _, _ = crear_use_case(open_data=provider)

    resultado = await use_case.ejecutar(crear_comando())

    assert resultado.pricing.factor_open_finance == Decimal("0.85")
    assert resultado.pricing.ajuste_open_data == Decimal("0.00")
    assert resultado.fuente_perfil == FuentePerfil.PARCIAL


async def test_fallan_ambos_proveedores_y_cache_usa_factor_estandar():
    provider = FakeOpenDataProvider()
    provider.error = OpenDataNoDisponibleError()
    use_case, _, _, _ = crear_use_case(
        perfil=OpenFinanceNoDisponibleError(),
        open_data=provider,
        cache=FakeOpenDataCache(falla=True),
    )

    resultado = await use_case.ejecutar(crear_comando())

    assert resultado.pricing.factor_open_finance == Decimal("1.00")
    assert resultado.pricing.factor_open_data == Decimal("1.00")
    assert resultado.pricing.prima_total == Decimal("59500.00")
    assert resultado.fuente_perfil == FuentePerfil.FALLBACK


async def test_cache_indisponible_no_bloquea_datos_open_data_validos():
    use_case, _, _, _ = crear_use_case(cache=FakeOpenDataCache(falla=True))

    resultado = await use_case.ejecutar(crear_comando())

    assert resultado.pricing.factor_open_data == Decimal("0.95")
    assert resultado.fuente_perfil == FuentePerfil.PROVEEDORES


async def test_sin_consentimiento_no_genera_cotizacion():
    use_case, _, _, _ = crear_use_case(
        perfil=ConsentimientoNoActivoError()
    )

    with pytest.raises(ConsentimientoNoActivoError):
        await use_case.ejecutar(crear_comando())


async def test_cliente_inexistente_no_genera_cotizacion():
    use_case, _, _, _ = crear_use_case(
        perfil=ClienteCotizacionNoEncontradoError()
    )

    with pytest.raises(ClienteCotizacionNoEncontradoError):
        await use_case.ejecutar(crear_comando())
