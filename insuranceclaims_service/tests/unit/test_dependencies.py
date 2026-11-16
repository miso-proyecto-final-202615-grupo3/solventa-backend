from unittest.mock import AsyncMock, MagicMock

from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.siniestros.repositories import SiniestroRepository
from src.infrastructure.persistence.siniestros_repository_impl import SqlAlchemySiniestroRepository
from src.presentation.dependencies import get_db, get_siniestro_repository


async def test_dependencia_usa_la_sesion_inyectada(db_session: AsyncSession):
    app = FastAPI()

    async def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db

    @app.get("/test")
    async def endpoint(repo: SiniestroRepository = Depends(get_siniestro_repository)):
        return {"correcto": isinstance(repo, SqlAlchemySiniestroRepository) and repo.session is db_session}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/test")).json() == {"correcto": True}


async def test_get_db_cierra_la_sesion(monkeypatch):
    session = MagicMock(spec=AsyncSession)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr("src.presentation.dependencies.SessionLocal", lambda: context)
    generator = get_db()
    assert await anext(generator) is session
    await generator.aclose()
    context.__aexit__.assert_awaited_once()
