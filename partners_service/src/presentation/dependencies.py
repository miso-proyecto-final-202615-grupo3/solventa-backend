import hmac
from collections.abc import AsyncGenerator

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.use_cases.registrar_socio_use_case import RegistrarSocioUseCase
from src.core.config import settings
from src.core.database import SessionLocal
from src.domain.socios.repositories import SocioRepository
from src.infrastructure.persistence.socio_repository_impl import SqlAlchemySocioRepository


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


def get_socio_repository(db: AsyncSession = Depends(get_db)) -> SocioRepository:
    return SqlAlchemySocioRepository(db)


def get_registrar_socio_use_case(
    repository: SocioRepository = Depends(get_socio_repository),
) -> RegistrarSocioUseCase:
    return RegistrarSocioUseCase(repository)


def require_internal_token(
    token: str | None = Header(default=None, alias="X-Partners-Internal-Token"),
) -> None:
    if not settings.PARTNERS_INTERNAL_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El servicio de socios no está configurado.",
        )
    if token is None or not hmac.compare_digest(token, settings.PARTNERS_INTERNAL_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticación interna requerida.",
        )
