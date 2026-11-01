import hashlib
import logging
from collections.abc import AsyncGenerator

from fastapi import Header

from src.core.config import settings
from src.infrastructure.gateways.identity_service_gateway import (
    IdentityServiceGateway,
)
from src.infrastructure.gateways.quotingengine_service_gateway import (
    QuotingEngineServiceGateway,
)
from src.presentation.errors import ApiError
from src.presentation.jwt_validator import (
    ClienteAutenticado,
    IdentityLookupUnavailableError,
    InvalidJwtError,
    get_cognito_jwt_validator,
)


logger = logging.getLogger("uvicorn.error")


def demo_sin_jwt_habilitada() -> bool:
    return settings.ENVIRONMENT.lower() == "development" and settings.ALLOW_DEMO_ACTIVATION_WITHOUT_JWT


def _log_auth(metodo: str, resultado: str, correlation_id: str | None, subject: str | None = None) -> None:
    # Auditoría sin datos personales: solo un hash corto del sub de Cognito.
    sub_hash = hashlib.sha256(subject.encode()).hexdigest()[:12] if subject else "-"
    logger.info("bff_auth metodo=%s resultado=%s sub_hash=%s correlation_id=%s", metodo, resultado, sub_hash, correlation_id)


def get_cliente_autenticado(
    authorization: str | None = Header(default=None),
    x_demo_correo: str | None = Header(default=None),
    x_correlation_id: str | None = Header(default=None),
) -> ClienteAutenticado:
    if demo_sin_jwt_habilitada() and x_demo_correo:
        _log_auth("demo", "aceptado", x_correlation_id)
        return ClienteAutenticado(correo=x_demo_correo, subject="demo")
    if not authorization or not authorization.startswith("Bearer "):
        _log_auth("ninguno", "rechazado", x_correlation_id)
        raise ApiError(401, "NO_AUTENTICADO", "Se requiere un token Bearer válido.")
    try:
        cliente = get_cognito_jwt_validator().validar(authorization.removeprefix("Bearer "))
    except InvalidJwtError as exc:
        _log_auth("cognito_jwt", "rechazado", x_correlation_id)
        raise ApiError(401, "NO_AUTENTICADO", "Token inválido o vencido.") from exc
    except IdentityLookupUnavailableError as exc:
        _log_auth("cognito_jwt", "cognito_no_disponible", x_correlation_id)
        raise ApiError(503, "SERVICIO_NO_DISPONIBLE", "No fue posible validar la sesión. Intenta de nuevo.") from exc
    _log_auth("cognito_jwt", "aceptado", x_correlation_id, cliente.subject)
    return cliente


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
