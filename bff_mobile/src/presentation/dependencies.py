from collections.abc import AsyncGenerator

from src.infrastructure.gateways.identity_service_gateway import (
    IdentityServiceGateway,
)
from src.infrastructure.gateways.quotingengine_service_gateway import (
    QuotingEngineServiceGateway,
)


async def get_identity_service_gateway() -> AsyncGenerator[IdentityServiceGateway, None]:
    gateway = IdentityServiceGateway()
    try:
        yield gateway
    finally:
        await gateway.aclose()


async def get_quotingengine_service_gateway() -> AsyncGenerator[
    QuotingEngineServiceGateway, None
]:
    gateway = QuotingEngineServiceGateway()
    try:
        yield gateway
    finally:
        await gateway.aclose()
