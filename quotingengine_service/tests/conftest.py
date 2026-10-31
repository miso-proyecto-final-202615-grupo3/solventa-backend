from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.core.database import Base

# sqlite en memoria no soporta schemas: compilar las tablas sin esquema
Base.metadata.schema = None

from src.infrastructure.persistence import models  # noqa: F401,E402
from src.infrastructure.cache.regla_rating_cache import ReglaRatingCache  # noqa: E402
from src.main import app  # noqa: E402
from src.presentation.dependencies import (  # noqa: E402
    get_db,
    get_perfil_cliente_gateway,
    get_regla_rating_cache,
)
from tests.fakes import FakePerfilGateway, FakeRedis  # noqa: E402


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def fake_gateway() -> FakePerfilGateway:
    return FakePerfilGateway()


@pytest.fixture
async def api_client(
    db_session: AsyncSession, fake_redis: FakeRedis, fake_gateway: FakePerfilGateway
) -> AsyncGenerator[AsyncClient, None]:
    """Cliente HTTP con BD sqlite, Redis falso y gateway de identidad falso."""

    async def _db():
        yield db_session

    cache = ReglaRatingCache(fake_redis, 300)
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_regla_rating_cache] = lambda: cache
    app.dependency_overrides[get_perfil_cliente_gateway] = lambda: fake_gateway
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
    app.dependency_overrides.clear()
