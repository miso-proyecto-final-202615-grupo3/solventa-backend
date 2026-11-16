"""Idempotencia concurrente contra PostgreSQL real (plan de HU4.1.1 §8).

Se ejecuta solo con `TEST_POSTGRES_URL`, por ejemplo con el Postgres de `docker compose up db`:
    TEST_POSTGRES_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/identity_db
"""
import asyncio
import os
import uuid

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.application.use_cases.reportar_siniestro_use_case import ReporteSiniestroCmd, ReportarSiniestroUseCase
from src.core.database import Base
from src.infrastructure.persistence.catalogo_tipos_siniestro_impl import (
    SqlAlchemyCatalogoTiposSiniestro,
    invalidar_cache,
)
from src.infrastructure.persistence.models import SiniestroModel
from src.infrastructure.persistence.seed_tipos_siniestro import sembrar_tipos_siniestro
from src.infrastructure.persistence.siniestros_repository_impl import SqlAlchemySiniestroRepository
from tests.fakes import AHORA, CLIENTE, PolizasFalsas, poliza

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL no está definida"),
]


async def test_reportes_simultaneos_con_la_misma_clave_crean_un_solo_siniestro():
    engine = create_async_engine(POSTGRES_URL)
    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    clave = str(uuid.uuid4())
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS insuranceclaims"))
        await conn.run_sync(Base.metadata.create_all)
    async with fabrica() as session:
        await sembrar_tipos_siniestro(session)
        await session.commit()
    invalidar_cache()
    polizas = PolizasFalsas(poliza())
    cmd = ReporteSiniestroCmd(
        cliente_id=CLIENTE,
        clave_idempotencia=clave,
        poliza_id=poliza().poliza_id,
        tipo="GASTO_MEDICO",
        descripcion="Prueba de concurrencia de idempotencia.",
        ocurrido_en=AHORA,
    )

    async def reportar():
        async with fabrica() as session:
            use_case = ReportarSiniestroUseCase(
                session, SqlAlchemySiniestroRepository(session), polizas,
                SqlAlchemyCatalogoTiposSiniestro(session), lambda: AHORA, ["VIGENTE"],
            )
            return await use_case.ejecutar(cmd, "corr-concurrencia")

    try:
        resultados = await asyncio.gather(*(reportar() for _ in range(10)))

        async with fabrica() as session:
            total = await session.scalar(
                select(func.count()).select_from(SiniestroModel).where(SiniestroModel.clave_idempotencia == clave)
            )
        assert total == 1
        assert len({r.siniestro.siniestro_id for r in resultados}) == 1
        assert sum(not r.repetido for r in resultados) == 1
    finally:
        async with fabrica() as session:
            await session.execute(delete(SiniestroModel).where(SiniestroModel.clave_idempotencia == clave))
            await session.commit()
        await engine.dispose()
        invalidar_cache()
