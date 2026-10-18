from collections.abc import AsyncGenerator

from src.infrastructure.gateways.identity_service_gateway import (
    IdentityServiceGateway,
)


async def get_identity_service_gateway() -> AsyncGenerator[IdentityServiceGateway, None]:
    gateway = IdentityServiceGateway()
    try:
        yield gateway
    finally:
        await gateway.aclose()
