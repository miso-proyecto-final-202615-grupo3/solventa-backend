from collections.abc import AsyncGenerator

from fastapi import Header, HTTPException, status

from src.core.config import settings
from src.infrastructure.gateways.identity_service_gateway import (
    IdentityServiceGateway,
)
from src.infrastructure.gateways.quotingengine_service_gateway import (
    QuotingEngineServiceGateway,
)
from src.presentation.jwt_validator import ClienteAutenticado, CognitoJwtValidator, InvalidJwtError


def demo_sin_jwt_habilitada() -> bool:
    return settings.ENVIRONMENT.lower() == "development" and settings.ALLOW_DEMO_ACTIVATION_WITHOUT_JWT


def get_cliente_autenticado(
    authorization: str | None = Header(default=None),
    x_demo_correo: str | None = Header(default=None),
) -> ClienteAutenticado:
    if demo_sin_jwt_habilitada() and x_demo_correo:
        return ClienteAutenticado(correo=x_demo_correo, subject="demo")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Se requiere un token Bearer válido.")
    try:
        return CognitoJwtValidator().validar(authorization.removeprefix("Bearer "))
    except InvalidJwtError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido o vencido.") from exc


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
