from collections.abc import AsyncGenerator
from datetime import timedelta

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.cotizaciones import CotizacionGateway
from src.application.ports.firmas import FirmaGateway
from src.application.use_cases.consultar_pago_use_case import (
    ConsultarPagoUseCase,
    ConsultarResumenPagoUseCase,
)
from src.application.use_cases.procesar_pago_prima_use_case import ProcesarPagoPrimaUseCase
from src.core.config import settings
from src.core.database import SessionLocal
from src.domain.pagos.entities import MetodoPago
from src.infrastructure.gateways.insurancepolicies_http_client import InsurancePoliciesHttpClient
from src.infrastructure.gateways.payment_provider_http_client import (
    ClienteProveedorPago,
    PayPalProveedor,
    TarjetaCreditoProveedor,
)
from src.infrastructure.gateways.quotingengine_http_client import QuotingEngineHttpClient
from src.infrastructure.persistence.evento_outbox_repository_impl import (
    SqlAlchemyEventoOutboxRepository,
)
from src.infrastructure.persistence.pago_prima_repository_impl import SqlAlchemyPagoPrimaRepository


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def get_cotizacion_gateway() -> AsyncGenerator[CotizacionGateway, None]:
    gateway = QuotingEngineHttpClient()
    try:
        yield gateway
    finally:
        await gateway.aclose()


async def get_firma_gateway() -> AsyncGenerator[FirmaGateway, None]:
    gateway = InsurancePoliciesHttpClient()
    try:
        yield gateway
    finally:
        await gateway.aclose()


async def get_proveedores_pago() -> AsyncGenerator[dict[MetodoPago, object], None]:
    cliente = ClienteProveedorPago()
    try:
        yield {
            MetodoPago.PAYPAL: PayPalProveedor(cliente),
            MetodoPago.TARJETA_CREDITO: TarjetaCreditoProveedor(cliente),
        }
    finally:
        await cliente.aclose()


def get_procesar_pago_prima_use_case(
    db: AsyncSession = Depends(get_db),
    cotizaciones: CotizacionGateway = Depends(get_cotizacion_gateway),
    firmas: FirmaGateway = Depends(get_firma_gateway),
    proveedores: dict = Depends(get_proveedores_pago),
) -> ProcesarPagoPrimaUseCase:
    return ProcesarPagoPrimaUseCase(
        SqlAlchemyPagoPrimaRepository(db),
        SqlAlchemyEventoOutboxRepository(db),
        cotizaciones,
        firmas,
        proveedores,
        settings.PAYMENT_PROVIDER_NAME,
        db.commit,
        db.rollback,
        settings.REQUIRE_FIRMA_DIGITAL,
        timedelta(seconds=settings.PAGO_PENDIENTE_TTL_SECONDS),
    )


def get_consultar_resumen_pago_use_case(
    cotizaciones: CotizacionGateway = Depends(get_cotizacion_gateway),
) -> ConsultarResumenPagoUseCase:
    return ConsultarResumenPagoUseCase(cotizaciones)


def get_consultar_pago_use_case(db: AsyncSession = Depends(get_db)) -> ConsultarPagoUseCase:
    return ConsultarPagoUseCase(SqlAlchemyPagoPrimaRepository(db))
