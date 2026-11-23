from collections.abc import AsyncGenerator

from fastapi import Header, HTTPException
from src.presentation.cliente_jwt_validator import (
    ClienteTokenConfiguracionError,
    ClienteTokenError,
    get_cognito_cliente_jwt_validator,
)

from src.infrastructure.gateways.identity_socios_gateway import (
    IdentitySociosGateway,
)
from src.infrastructure.gateways.identity_service_gateway import (
    IdentityServiceGateway,
)
from src.infrastructure.gateways.insurancepolicies_service_gateway import (
    InsurancePoliciesServiceGateway,
)
from src.infrastructure.gateways.quotingengine_service_gateway import (
    QuotingEngineServiceGateway,
)
from src.infrastructure.gateways.payments_service_gateway import (
    PaymentsServiceGateway,
)
from src.presentation.auditor_jwt_validator import (
    AuditorTokenConfiguracionError,
    AuditorTokenError,
    get_cognito_auditor_jwt_validator,
)
from src.presentation.socios_admin_jwt_validator import (
    SociosAdminTokenConfiguracionError,
    SociosAdminTokenError,
    get_cognito_socios_admin_jwt_validator,
)


async def get_identity_service_gateway() -> AsyncGenerator[IdentityServiceGateway, None]:
    gateway = IdentityServiceGateway()
    try:
        yield gateway
    finally:
        await gateway.aclose()


async def get_identity_socios_gateway() -> AsyncGenerator[IdentitySociosGateway, None]:
    gateway = IdentitySociosGateway()
    try:
        yield gateway
    finally:
        await gateway.aclose()


async def get_payments_service_gateway() -> AsyncGenerator[PaymentsServiceGateway, None]:
    gateway = PaymentsServiceGateway()
    try:
        yield gateway
    finally:
        await gateway.aclose()


def require_cliente(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer ") or not authorization[7:].strip():
        raise HTTPException(status_code=401, detail="Autenticación requerida.")
    try:
        return get_cognito_cliente_jwt_validator().validar(authorization[7:])
    except ClienteTokenConfiguracionError as exc:
        raise HTTPException(status_code=503, detail="Autenticación no configurada.") from exc
    except ClienteTokenError as exc:
        raise HTTPException(status_code=401, detail="Token inválido o vencido.") from exc


def require_auditor(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Autenticación requerida.")
    try:
        return get_cognito_auditor_jwt_validator().validar(authorization[7:])
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Acceso exclusivo para auditores.") from exc
    except AuditorTokenConfiguracionError as exc:
        raise HTTPException(
            status_code=503, detail="Autenticación de auditoría no configurada."
        ) from exc
    except AuditorTokenError as exc:
        raise HTTPException(status_code=401, detail="Token inválido o vencido.") from exc


def require_socios_admin(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Autenticación requerida.")
    try:
        return get_cognito_socios_admin_jwt_validator().validar(authorization[7:])
    except PermissionError as exc:
        raise HTTPException(
            status_code=403, detail="Acceso exclusivo para administradores de socios."
        ) from exc
    except SociosAdminTokenConfiguracionError as exc:
        raise HTTPException(
            status_code=503, detail="Autenticación de socios no configurada."
        ) from exc
    except SociosAdminTokenError as exc:
        raise HTTPException(status_code=401, detail="Token inválido o vencido.") from exc


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
