from collections.abc import AsyncGenerator

from src.infrastructure.gateways.identity_service_gateway import (
    IdentityServiceGateway,
)
from src.infrastructure.gateways.insurancepolicies_service_gateway import (
    InsurancePoliciesServiceGateway,
)
from src.infrastructure.gateways.quotingengine_service_gateway import (
    QuotingEngineServiceGateway,
)
from src.infrastructure.gateways.insurancepolicies_service_gateway import (
    InsurancePoliciesServiceGateway,
)


def get_identity_service_gateway() -> IdentityServiceGateway:
    return IdentityServiceGateway()


async def get_insurancepolicies_service_gateway() -> AsyncGenerator[
    InsurancePoliciesServiceGateway, None
]:
    gateway = InsurancePoliciesServiceGateway()
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


async def get_insurancepolicies_service_gateway() -> AsyncGenerator[
    InsurancePoliciesServiceGateway, None
]:
    gateway = InsurancePoliciesServiceGateway()
    try:
        yield gateway
    finally:
        await gateway.aclose()
