from collections.abc import AsyncGenerator
from functools import lru_cache

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.use_cases.capturar_firma_digital_use_case import (
    CapturarFirmaDigitalUseCase,
)
from src.application.use_cases.consultar_firma_digital_use_case import (
    ConsultarFirmaDigitalUseCase,
)
from src.core.config import settings
from src.core.database import SessionLocal
from src.domain.firmas.repositories import AlmacenamientoFirmaRepository
from src.domain.polizas.repositories import PolizaRepository
from src.infrastructure.persistence.firma_digital_repository_impl import (
    SqlAlchemyFirmaDigitalRepository,
)
from src.infrastructure.persistence.poliza_repository_impl import (
    SqlAlchemyPolizaRepository,
)
from src.infrastructure.storage.firma_local_repository import (
    LocalAlmacenamientoFirmaRepository,
)
from src.infrastructure.storage.firma_s3_repository import (
    S3AlmacenamientoFirmaRepository,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


def get_poliza_repository(
    db: AsyncSession = Depends(get_db),
) -> PolizaRepository:
    return SqlAlchemyPolizaRepository(db)


@lru_cache(maxsize=1)
def get_almacenamiento_firma_repository() -> AlmacenamientoFirmaRepository:
    if settings.FIRMA_STORAGE == "local":
        return LocalAlmacenamientoFirmaRepository(settings.FIRMA_LOCAL_BASE_DIR)
    if settings.FIRMA_STORAGE == "s3":
        return S3AlmacenamientoFirmaRepository()
    raise ValueError("Tipo de almacenamiento de firmas no válido.")


def get_capturar_firma_digital_use_case(
    db: AsyncSession = Depends(get_db),
    almacenamiento: AlmacenamientoFirmaRepository = Depends(
        get_almacenamiento_firma_repository
    ),
) -> CapturarFirmaDigitalUseCase:
    return CapturarFirmaDigitalUseCase(
        SqlAlchemyFirmaDigitalRepository(db),
        almacenamiento,
        db.commit,
        db.rollback,
        settings.FIRMA_MAX_BYTES,
        settings.FIRMA_PROVEEDOR,
    )


def get_consultar_firma_digital_use_case(
    db: AsyncSession = Depends(get_db),
) -> ConsultarFirmaDigitalUseCase:
    return ConsultarFirmaDigitalUseCase(SqlAlchemyFirmaDigitalRepository(db))
