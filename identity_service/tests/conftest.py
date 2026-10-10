from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.core.database import Base
from src.infrastructure.persistence import models  # noqa: F401
from src.main import app
from src.presentation.dependencies import get_db, get_identity_provider

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


class FakeIdentityProvider:
    def __init__(self):
        self.registrados: list[tuple[str, str]] = []
        self.eliminados: list[str] = []
        self.fallar_registro: bool = False

    async def registrar_usuario(self, correo: str, password: str) -> None:
        if self.fallar_registro:
            raise RuntimeError("Cognito no disponible")
        self.registrados.append((correo, password))

    async def eliminar_usuario(self, correo: str) -> None:
        self.eliminados.append(correo)


@pytest.fixture
def fake_identity_provider() -> FakeIdentityProvider:
    return FakeIdentityProvider()


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


@pytest.fixture
async def db_engine():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(
    db_engine,
) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with factory() as session:
        yield session