from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.identity_provider import IdentityProvider
from src.application.use_cases.autenticar_cliente_use_case import (
    AutenticarClienteUseCase,
)
from src.application.use_cases.registrar_cliente_use_case import RegistrarClienteUseCase
from src.core.database import SessionLocal
from src.domain.clientes.repositories import ClienteRepository
from src.infrastructure.gateways.cognito_identity_provider import CognitoIdentityProvider
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
    return CognitoIdentityProvider()


def get_registrar_cliente_use_case(
    repository: ClienteRepository = Depends(get_cliente_repository),
    identity_provider: IdentityProvider = Depends(get_identity_provider),
) -> RegistrarClienteUseCase:
    return RegistrarClienteUseCase(repository, identity_provider)


def get_autenticar_cliente_use_case(
    identity_provider: IdentityProvider = Depends(get_identity_provider),
) -> AutenticarClienteUseCase:
    return AutenticarClienteUseCase(identity_provider)