import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
import logging
import uuid
from typing import Any

from src.application.ports.perfilamiento import (
    ClienteCotizacionNoEncontradoError,
    ConsentimientoNoActivoError,
    OpenDataCachePort,
    OpenDataNoDisponibleError,
    OpenDataProvider,
    OpenFinanceNoDisponibleError,
    PerfilFinancieroProvider,
)
from src.domain.open_data import CategoriaOpenData
from src.domain.pricing import PerfilFinanciero, ResultadoPricing, calcular_pricing

logger = logging.getLogger(__name__)


class FuentePerfil(StrEnum):
    PROVEEDORES = "PROVEEDORES"
    CACHE = "CACHE"
    FALLBACK = "FALLBACK"
    PARCIAL = "PARCIAL"


@dataclass(frozen=True)
class CotizarCommand:
    cliente_id: uuid.UUID
    saldo_credito: Decimal
    ubicacion: dict[str, Any]


@dataclass(frozen=True)
class CotizacionGenerada:
    cotizacion_id: uuid.UUID
    pricing: ResultadoPricing
    categoria_open_data: CategoriaOpenData
    fuente_perfil: FuentePerfil
    open_finance_personalizado: bool
    vigencia_hasta: datetime


class GenerarCotizacionUseCase:
    def __init__(
        self,
        perfil_financiero_provider: PerfilFinancieroProvider,
        open_data_provider: OpenDataProvider,
        open_data_cache: OpenDataCachePort,
    ) -> None:
        self.perfil_financiero_provider = perfil_financiero_provider
        self.open_data_provider = open_data_provider
        self.open_data_cache = open_data_cache

    async def ejecutar(self, command: CotizarCommand) -> CotizacionGenerada:
        perfil_open_finance, perfil_open_data = await asyncio.gather(
            self.perfil_financiero_provider.obtener_perfil_financiero(
                command.cliente_id
            ),
            self.open_data_provider.obtener_riesgo_territorial(
                command.ubicacion
            ),
            return_exceptions=True,
        )

        if isinstance(perfil_open_finance, ConsentimientoNoActivoError):
            raise perfil_open_finance
        if isinstance(perfil_open_finance, ClienteCotizacionNoEncontradoError):
            raise perfil_open_finance
        if isinstance(perfil_open_finance, OpenFinanceNoDisponibleError):
            perfil_financiero = _perfil_financiero_neutral()
            open_finance_disponible = False
        elif isinstance(perfil_open_finance, Exception):
            raise perfil_open_finance
        else:
            perfil_financiero = perfil_open_finance
            open_finance_disponible = True

        open_data_en_cache = False
        if isinstance(perfil_open_data, OpenDataNoDisponibleError):
            try:
                categoria = await self.open_data_cache.obtener(command.ubicacion)
            except Exception:
                logger.warning("No se pudo consultar la caché Open Data.")
                categoria = None
            if categoria is None:
                categoria = CategoriaOpenData.ESTANDAR
            else:
                open_data_en_cache = True
        elif isinstance(perfil_open_data, Exception):
            raise perfil_open_data
        else:
            categoria = perfil_open_data.categoria
            try:
                await self.open_data_cache.guardar(
                    command.ubicacion, perfil_open_data
                )
            except Exception:
                logger.warning("No se pudo guardar la caché Open Data.")

        pricing = calcular_pricing(
            saldo_credito=command.saldo_credito,
            perfil=perfil_financiero,
            factor_open_data=categoria.factor,
        )
        fuente = _fuente_perfil(
            open_finance_disponible=open_finance_disponible,
            open_data_disponible=not isinstance(
                perfil_open_data, OpenDataNoDisponibleError
            ),
            open_data_en_cache=open_data_en_cache,
        )
        return CotizacionGenerada(
            cotizacion_id=uuid.uuid4(),
            pricing=pricing,
            categoria_open_data=categoria,
            fuente_perfil=fuente,
            open_finance_personalizado=open_finance_disponible,
            vigencia_hasta=datetime.now(UTC) + timedelta(days=1),
        )


def _perfil_financiero_neutral() -> PerfilFinanciero:
    return PerfilFinanciero(
        ingreso_mensual=None,
        ahorros_liquidos=None,
        dti_pct=None,
        sobregiros_12_meses=None,
        score=None,
    )


def _fuente_perfil(
    open_finance_disponible: bool,
    open_data_disponible: bool,
    open_data_en_cache: bool,
) -> FuentePerfil:
    if open_finance_disponible and open_data_disponible:
        return FuentePerfil.PROVEEDORES
    if not open_finance_disponible and not open_data_disponible:
        if open_data_en_cache:
            return FuentePerfil.PARCIAL
        return FuentePerfil.FALLBACK
    if open_data_en_cache:
        return FuentePerfil.PARCIAL
    return FuentePerfil.PARCIAL
