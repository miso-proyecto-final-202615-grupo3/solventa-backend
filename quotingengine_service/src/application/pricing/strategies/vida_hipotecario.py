import asyncio
import logging
import uuid
from decimal import Decimal
from typing import Any

from src.application.ports.perfil_cliente_gateway import (
    ConsentimientoNoOtorgadoError,
    PerfilClienteGateway,
    PerfilNoDisponibleError,
)
from src.application.ports.open_data_gateway import (
    OpenDataCachePort,
    OpenDataGateway,
    OpenDataNoDisponibleError,
)
from src.application.pricing.strategies.tasa_base import TasaBasePricingStrategy
from src.application.pricing.strategies.tasa_base import redondear
from src.application.pricing.strategy import (
    AjustePrima,
    ContextoPricing,
    SenalesPricing,
    TipoAjuste,
)
from src.domain.open_data import CategoriaOpenData, PerfilTerritorial

logger = logging.getLogger(__name__)

DEGRADACION_PERFIL_NO_DISPONIBLE = "PERFIL_NO_DISPONIBLE"
DEGRADACION_OPEN_FINANCE_NO_DISPONIBLE = "OPEN_FINANCE_NO_DISPONIBLE"
DEGRADACION_OPEN_DATA_NO_DISPONIBLE = "OPEN_DATA_NO_DISPONIBLE"
DEGRADACION_OPEN_DATA_CACHE = "OPEN_DATA_CACHE"

_FACTOR_OPEN_FINANCE = {
    "A": Decimal("0.85"),
    "B": Decimal("1.00"),
    "C": Decimal("1.20"),
}


class VidaHipotecarioPricingStrategy(TasaBasePricingStrategy):
    """Seguro de vida hipotecario.

    Consulta Open Finance a través de Identity y el riesgo territorial con Open Data.
    Las indisponibilidades degradan a factores neutrales; la falta de consentimiento
    se propaga para que el endpoint rechace la cotización.
    """

    codigo_producto = "VIDA_HIPOTECARIO"

    def __init__(
        self,
        perfil_gateway: PerfilClienteGateway,
        open_data_gateway: OpenDataGateway,
        open_data_cache: OpenDataCachePort | None = None,
    ) -> None:
        self._perfil_gateway = perfil_gateway
        self._open_data_gateway = open_data_gateway
        self._open_data_cache = open_data_cache

    async def recolectar_senales(
        self, cliente_id: uuid.UUID, parametros: dict[str, Any] | None = None
    ) -> SenalesPricing:
        ubicacion = (parametros or {}).get("ubicacion", {})
        perfil, (perfil_territorial, degradacion_open_data) = await asyncio.gather(
            self._obtener_perfil(cliente_id),
            self._obtener_perfil_territorial(ubicacion),
        )
        degradaciones = []
        if isinstance(perfil, PerfilNoDisponibleError):
            logger.warning(
                "Perfil del cliente %s no disponible; se aplica factor neutral",
                cliente_id,
            )
            perfil = None
            degradaciones.append(DEGRADACION_PERFIL_NO_DISPONIBLE)
        elif perfil is not None and not perfil.open_finance_disponible:
            degradaciones.append(DEGRADACION_OPEN_FINANCE_NO_DISPONIBLE)
        if degradacion_open_data:
            degradaciones.append(degradacion_open_data)
        return SenalesPricing(
            perfil=perfil,
            perfil_territorial=perfil_territorial,
            degradaciones=tuple(degradaciones),
        )

    async def _obtener_perfil(self, cliente_id: uuid.UUID):
        try:
            return await self._perfil_gateway.obtener_perfil(cliente_id)
        except ConsentimientoNoOtorgadoError:
            raise
        except PerfilNoDisponibleError as exc:
            return exc

    async def _obtener_perfil_territorial(
        self, ubicacion: dict[str, Any]
    ) -> tuple[PerfilTerritorial, str | None]:
        try:
            perfil = await self._open_data_gateway.obtener_riesgo(ubicacion)
        except OpenDataNoDisponibleError:
            if self._open_data_cache is not None:
                try:
                    categoria = await self._open_data_cache.obtener(ubicacion)
                except Exception:
                    logger.warning("No se pudo consultar la caché Open Data.")
                    categoria = None
                if categoria is not None:
                    return PerfilTerritorial(categoria), DEGRADACION_OPEN_DATA_CACHE
            return (
                PerfilTerritorial(CategoriaOpenData.ESTANDAR),
                DEGRADACION_OPEN_DATA_NO_DISPONIBLE,
            )
        if self._open_data_cache is not None:
            try:
                await self._open_data_cache.guardar(ubicacion, perfil)
            except Exception:
                logger.warning("No se pudo actualizar la caché Open Data.")
        return perfil, None

    def calcular_ajustes(
        self, contexto: ContextoPricing, prima_base: Decimal
    ) -> list[AjustePrima]:
        categoria_financiera = _clasificar_open_finance(contexto.senales.perfil)
        factor_financiero = _FACTOR_OPEN_FINANCE[categoria_financiera]
        ajustes = []
        if factor_financiero != Decimal("1.00"):
            diferencia = redondear(prima_base * abs(factor_financiero - 1))
            ajustes.append(
                AjustePrima(
                    concepto="OPEN_FINANCE",
                    tipo=(
                        TipoAjuste.DEDUCCION
                        if factor_financiero < 1
                        else TipoAjuste.RECARGO
                    ),
                    valor=diferencia,
                    motivo=f"Perfil financiero categoría {categoria_financiera}.",
                )
            )

        categoria_territorial = (
            contexto.senales.perfil_territorial.categoria
            if contexto.senales.perfil_territorial
            else CategoriaOpenData.ESTANDAR
        )
        factor_territorial = categoria_territorial.factor
        prima_tras_open_finance = prima_base + sum(
            (
                -ajuste.valor
                if ajuste.tipo == TipoAjuste.DEDUCCION
                else ajuste.valor
                for ajuste in ajustes
            ),
            Decimal("0"),
        )
        if factor_territorial != Decimal("1.00"):
            diferencia = redondear(
                prima_tras_open_finance * abs(factor_territorial - 1)
            )
            ajustes.append(
                AjustePrima(
                    concepto="OPEN_DATA",
                    tipo=(
                        TipoAjuste.DEDUCCION
                        if factor_territorial < 1
                        else TipoAjuste.RECARGO
                    ),
                    valor=diferencia,
                    motivo=f"Riesgo territorial categoría {categoria_territorial.value}.",
                )
            )
        return ajustes


def _clasificar_open_finance(perfil) -> str:
    if perfil is None or not perfil.open_finance_disponible:
        return "B"
    if (
        (perfil.dti_pct is not None and perfil.dti_pct > 50)
        or (perfil.score is not None and perfil.score < 600)
        or (perfil.sobregiros_12_meses is not None and perfil.sobregiros_12_meses >= 3)
    ):
        return "C"
    reserva_suficiente = (
        perfil.ingreso_mensual is not None
        and perfil.ingreso_mensual > 0
        and perfil.ahorros_liquidos is not None
        and perfil.ahorros_liquidos >= perfil.ingreso_mensual * 3
    )
    if (
        perfil.dti_pct is not None
        and perfil.dti_pct <= 30
        and perfil.score is not None
        and perfil.score >= 800
        and perfil.sobregiros_12_meses == 0
        and reserva_suficiente
    ):
        return "A"
    return "B"
