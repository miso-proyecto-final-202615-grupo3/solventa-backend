from collections.abc import AsyncGenerator

import httpx
from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.perfil_cliente_gateway import PerfilClienteGateway
from src.application.ports.open_data_gateway import OpenDataCachePort, OpenDataGateway
from src.application.ports.regla_rating_cache import ReglaRatingCachePort
from src.application.pricing.registry import PricingStrategyRegistry
from src.application.pricing.strategies.otros_productos import (
    MicroseguroVidaPricingStrategy,
    ParametricoPricingStrategy,
    ProteccionDispositivosPricingStrategy,
    ProteccionPagosPricingStrategy,
    ViajePricingStrategy,
)
from src.application.pricing.strategies.vida_hipotecario import (
    VidaHipotecarioPricingStrategy,
)
from src.application.services.regla_rating_resolver import ReglaRatingResolver
from src.application.use_cases.consultar_catalogo_use_case import (
    ConsultarCatalogoUseCase,
)
from src.application.use_cases.solicitar_cotizacion_use_case import (
    SolicitarCotizacionUseCase,
)
from src.core.config import settings
from src.core.database import SessionLocal
from src.infrastructure.cache.regla_rating_cache import ReglaRatingCache
from src.infrastructure.cache.open_data_redis_cache import OpenDataRedisCache
from src.infrastructure.gateways.identity_grpc_client import IdentityGrpcClient
from src.infrastructure.gateways.open_data_http_client import OpenDataHttpClient
from src.infrastructure.persistence.auditoria_decision_repository_impl import (
    SqlAlchemyAuditoriaDecisionRepository,
)
from src.infrastructure.persistence.cobertura_repository_impl import (
    SqlAlchemyCoberturaRepository,
)
from src.infrastructure.persistence.cotizacion_cobertura_repository_impl import (
    SqlAlchemyCotizacionCoberturaRepository,
)
from src.infrastructure.persistence.cotizacion_repository_impl import (
    SqlAlchemyCotizacionRepository,
)
from src.infrastructure.persistence.producto_seguro_repository_impl import (
    SqlAlchemyProductoSeguroRepository,
)
from src.infrastructure.persistence.regla_rating_repository_impl import (
    SqlAlchemyReglaRatingRepository,
)
from src.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork

_redis_client = Redis.from_url(
    settings.REDIS_ENDPOINT,
    password=settings.REDIS_AUTH_TOKEN or None,
    decode_responses=True,
)
_regla_rating_cache = ReglaRatingCache(_redis_client, settings.RATING_CACHE_TTL_SECONDS)
_perfil_gateway: IdentityGrpcClient | None = None
_open_data_http = httpx.AsyncClient(timeout=settings.OPEN_DATA_TIMEOUT_SECONDS)
_open_data_cache = OpenDataRedisCache(
    _redis_client, settings.OPEN_DATA_CACHE_TTL_SECONDS
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


def get_regla_rating_cache() -> ReglaRatingCachePort:
    return _regla_rating_cache


def get_perfil_cliente_gateway() -> PerfilClienteGateway:
    if _perfil_gateway is None:
        raise RuntimeError("El cliente gRPC de identidad no fue inicializado.")
    return _perfil_gateway


async def inicializar_recursos(app) -> None:
    global _perfil_gateway
    _perfil_gateway = IdentityGrpcClient()


def get_open_data_gateway() -> OpenDataGateway:
    return OpenDataHttpClient(_open_data_http)


def get_open_data_cache() -> OpenDataCachePort:
    return _open_data_cache


async def cerrar_recursos() -> None:
    global _perfil_gateway
    await _regla_rating_cache.cerrar()
    if _perfil_gateway is not None:
        await _perfil_gateway.cerrar()
        _perfil_gateway = None
    await _open_data_http.aclose()


def get_regla_rating_resolver(
    db: AsyncSession = Depends(get_db),
    cache: ReglaRatingCachePort = Depends(get_regla_rating_cache),
) -> ReglaRatingResolver:
    return ReglaRatingResolver(SqlAlchemyReglaRatingRepository(db), cache)


def get_pricing_registry(
    gateway: PerfilClienteGateway = Depends(get_perfil_cliente_gateway),
    open_data: OpenDataGateway = Depends(get_open_data_gateway),
    open_data_cache: OpenDataCachePort = Depends(get_open_data_cache),
) -> PricingStrategyRegistry:
    return PricingStrategyRegistry(
        [
            VidaHipotecarioPricingStrategy(gateway, open_data, open_data_cache),
            ProteccionPagosPricingStrategy(),
            ViajePricingStrategy(),
            ProteccionDispositivosPricingStrategy(),
            MicroseguroVidaPricingStrategy(),
            ParametricoPricingStrategy(),
        ]
    )


def get_consultar_catalogo_use_case(
    db: AsyncSession = Depends(get_db),
    resolver: ReglaRatingResolver = Depends(get_regla_rating_resolver),
) -> ConsultarCatalogoUseCase:
    return ConsultarCatalogoUseCase(
        SqlAlchemyProductoSeguroRepository(db),
        SqlAlchemyCoberturaRepository(db),
        resolver,
    )


def get_solicitar_cotizacion_use_case(
    db: AsyncSession = Depends(get_db),
    resolver: ReglaRatingResolver = Depends(get_regla_rating_resolver),
    registry: PricingStrategyRegistry = Depends(get_pricing_registry),
) -> SolicitarCotizacionUseCase:
    return SolicitarCotizacionUseCase(
        SqlAlchemyProductoSeguroRepository(db),
        SqlAlchemyCoberturaRepository(db),
        SqlAlchemyCotizacionRepository(db),
        SqlAlchemyCotizacionCoberturaRepository(db),
        SqlAlchemyAuditoriaDecisionRepository(db),
        resolver,
        registry,
        SqlAlchemyUnitOfWork(db),
        settings.COTIZACION_VIGENCIA_DIAS,
    )
