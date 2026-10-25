from collections.abc import AsyncIterator

from fastapi import Request

from src.infrastructure.gateways.identity_service_gateway import (
    IdentityServiceGateway,
)
from src.infrastructure.gateways.cotizacion_service_gateway import (
    CotizacionServiceGateway,
)


def get_identity_service_gateway() -> IdentityServiceGateway:
    return IdentityServiceGateway()


def get_cotizacion_service_gateway(
    request: Request,
) -> CotizacionServiceGateway:
    return request.app.state.cotizacion_service_gateway
