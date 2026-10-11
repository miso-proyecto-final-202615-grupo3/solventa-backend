from src.infrastructure.gateways.identity_service_gateway import (
    IdentityServiceGateway,
)


def get_identity_service_gateway() -> IdentityServiceGateway:
    return IdentityServiceGateway()