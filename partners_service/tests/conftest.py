from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.core.config import settings
from src.core.database import Base
from src.domain.socios.repositories import SocioRepository
from src.infrastructure.persistence import models  # noqa: F401
from src.main import app
from src.domain.socios.entities import Socio, EventoSocio


class InMemorySocioRepository(SocioRepository):
    def __init__(self) -> None:
        self.socios: list[Socio] = []
        self.eventos: list[EventoSocio] = []

    async def registrar(self, socio: Socio, evento: EventoSocio) -> None:
        self.socios.append(socio)
        self.eventos.append(evento)


@pytest.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        execution_options={"schema_translate_map": {"partners": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def socios_client(monkeypatch) -> AsyncGenerator[tuple[AsyncClient, InMemorySocioRepository], None]:
    from src.presentation.dependencies import get_socio_repository

    repository = InMemorySocioRepository()
    monkeypatch.setattr(settings, "PARTNERS_INTERNAL_TOKEN", "test-internal-token")
    app.dependency_overrides[get_socio_repository] = lambda: repository
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, repository
    app.dependency_overrides.clear()
