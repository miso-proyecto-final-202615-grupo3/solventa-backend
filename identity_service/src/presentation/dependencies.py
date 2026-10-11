from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.identity_provider import IdentityProvider
from src.application.ports.kyc import KycVerifier
from src.application.use_cases.autenticar_cliente_use_case import (
    AutenticarClienteUseCase,
)
from src.application.use_cases.registrar_cliente_use_case import RegistrarClienteUseCase
from src.application.use_cases.verificar_kyc_use_case import VerificarKycUseCase
from src.core.config import settings
from src.core.database import SessionLocal
from src.domain.clientes.repositories import ClienteRepository
from src.infrastructure.gateways.cognito_identity_provider import CognitoIdentityProvider
from src.infrastructure.gateways.kyc_http_client import KycHttpClient
from src.infrastructure.gateways.noop_identity_provider import NoopIdentityProvider
from src.infrastructure.persistence.cliente_repository_impl import (
    SqlAlchemyClienteRepository,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


def get_cliente_repository(
    db: AsyncSession = Depends(get_db),
) -> ClienteRepository:
    return SqlAlchemyClienteRepository(db)


def get_identity_provider() -> IdentityProvider:
    if settings.COGNITO_ENABLED:
        return CognitoIdentityProvider()
    return NoopIdentityProvider()


def get_registrar_cliente_use_case(
    repository: ClienteRepository = Depends(get_cliente_repository),
    identity_provider: IdentityProvider = Depends(get_identity_provider),
) -> RegistrarClienteUseCase:
    return RegistrarClienteUseCase(repository, identity_provider)


def get_autenticar_cliente_use_case(
    identity_provider: IdentityProvider = Depends(get_identity_provider),
) -> AutenticarClienteUseCase:
    return AutenticarClienteUseCase(identity_provider)


def get_kyc_verifier() -> KycVerifier:
    return KycHttpClient()


def get_verificar_kyc_use_case(
    repository: ClienteRepository = Depends(get_cliente_repository),
    kyc_verifier: KycVerifier = Depends(get_kyc_verifier),
) -> VerificarKycUseCase:
    return VerificarKycUseCase(repository, kyc_verifier)