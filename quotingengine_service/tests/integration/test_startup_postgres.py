import asyncio
import os
import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import src.main as main
from src.infrastructure.persistence.models import (
    CoberturaModel,
    ProductoSeguroModel,
    ReglaRatingModel,
)
from src.infrastructure.persistence.seed import CATALOGO, sembrar_catalogo


@pytest.fixture
async def postgres_startup(monkeypatch):
    database_url = os.environ.get("TEST_STARTUP_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_STARTUP_DATABASE_URL no está configurada")

    identifier = uuid.uuid4().hex
    schema = f"startup_test_{identifier}"
    lock_key = int(identifier[:8], 16) & 0x7FFFFFFF
    engine = create_async_engine(
        database_url,
        execution_options={"schema_translate_map": {None: schema}},
    )
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    def startup_sql(statement):
        if statement == "CREATE SCHEMA IF NOT EXISTS quotingengine":
            statement = f"CREATE SCHEMA IF NOT EXISTS {schema}"
        elif statement == "SELECT pg_advisory_xact_lock(1397705812, 2)":
            statement = f"SELECT pg_advisory_xact_lock(1397705812, {lock_key})"
        return text(statement)

    monkeypatch.setattr(main, "text", startup_sql)
    monkeypatch.setattr(main, "SessionLocal", factory)
    monkeypatch.setattr(main, "inicializar_recursos", AsyncMock())
    monkeypatch.setattr(main, "cerrar_recursos", AsyncMock())
    monkeypatch.setattr(main.settings, "SEED_ON_STARTUP", True)
    try:
        yield engine, factory, schema
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        await engine.dispose()


async def test_cinco_arranques_serializados_crean_un_catalogo(postgres_startup, monkeypatch):
    _, factory, _ = postgres_startup
    active = 0
    maximum_active = 0
    created = []

    async def seed_observado(session):
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        try:
            await asyncio.sleep(0.05)
            count = await sembrar_catalogo(session)
            created.append(count)
            return count
        finally:
            active -= 1

    monkeypatch.setattr(main, "sembrar_catalogo", seed_observado)

    async def arrancar():
        async with main.lifespan(main.FastAPI()):
            pass

    async with asyncio.timeout(30):
        async with asyncio.TaskGroup() as group:
            for _ in range(5):
                group.create_task(arrancar())

    assert maximum_active == 1
    assert sorted(created) == [0, 0, 0, 0, len(CATALOGO)]
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(ProductoSeguroModel)) == len(CATALOGO)
        assert await session.scalar(select(func.count()).select_from(CoberturaModel)) == sum(
            len(item["coberturas"]) for item in CATALOGO
        )
        assert await session.scalar(select(func.count()).select_from(ReglaRatingModel)) == len(CATALOGO)


async def test_error_de_seed_revierte_esquema_y_permite_reintento(postgres_startup, monkeypatch):
    engine, factory, schema = postgres_startup

    async def seed_fallido(session):
        await sembrar_catalogo(session)
        raise RuntimeError("seed fallido")

    monkeypatch.setattr(main, "sembrar_catalogo", seed_fallido)
    with pytest.raises(RuntimeError, match="seed fallido"):
        async with main.lifespan(main.FastAPI()):
            pytest.fail("el servicio no debe arrancar")

    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = :schema)"),
            {"schema": schema},
        )
        assert result.scalar_one() is False

    monkeypatch.setattr(main, "sembrar_catalogo", sembrar_catalogo)
    async with main.lifespan(main.FastAPI()):
        async with factory() as session:
            assert await session.scalar(select(func.count()).select_from(ProductoSeguroModel)) == len(CATALOGO)
