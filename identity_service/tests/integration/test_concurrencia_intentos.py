"""Concurrencia real en PostgreSQL (criterio de terminado de HU3.1.1).

Se ejecuta solo con una base PostgreSQL disponible, por ejemplo la de `docker compose`:

    POSTGRES_TEST_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/appdata \
        python -m pytest -m postgres tests/integration/test_concurrencia_intentos.py
"""
import asyncio
import os
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.application.ports.liveness import LivenessVerification, LivenessVerificationPort
from src.application.use_cases.verificar_activacion_movil_use_case import (
    IntentosActivacionAgotadosError,
    VerificarActivacionMovilUseCase,
)
from src.core.database import Base
from src.infrastructure.persistence.activacion_movil_repository_impl import (
    SqlAlchemyActivacionMovilRepository,
)
from src.infrastructure.persistence.cliente_repository_impl import SqlAlchemyClienteRepository
from src.infrastructure.persistence.models import (
    ClienteModel,
    DispositivoVinculadoModel,
    IntentoPruebaVidaModel,
    SesionActivacionModel,
)

POSTGRES_URL = os.getenv("POSTGRES_TEST_URL")
SCHEMA = "identity_concurrencia_test"

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not POSTGRES_URL, reason="Requiere POSTGRES_TEST_URL (PostgreSQL de docker compose)."),
]


class LivenessLento(LivenessVerificationPort):
    """Simula al adaptador tardando, para que las dos verificaciones se crucen."""

    def __init__(self, aprobado: bool):
        self.aprobado = aprobado

    async def start_session(self, *args, **kwargs):
        raise AssertionError

    async def cancel_session(self, *args, **kwargs):
        raise AssertionError

    async def verify(self, session_id, *args, **kwargs):
        await asyncio.sleep(0.2)
        return LivenessVerification(f"folio-{session_id}", self.aprobado, None if self.aprobado else "GESTO_NO_DETECTADO")


@pytest.fixture
async def factory():
    # Esquema aislado y desechable. conftest.py quita el esquema "identity" para SQLite, así que se
    # traducen ambos casos (None e "identity") al esquema de prueba.
    engine = create_async_engine(
        POSTGRES_URL, execution_options={"schema_translate_map": {None: SCHEMA, "identity": SCHEMA}}
    )
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        await conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
    await engine.dispose()


async def _preparar(factory, rechazados_previos: int, sesiones: int):
    ahora = datetime.now(UTC)
    async with factory() as db:
        cliente = ClienteModel(
            nombres="Ana", apellidos="Pérez", tipo_documento="CC", numero_identificacion="1020304050",
            correo="ana@example.com", fecha_nacimiento=date(1990, 1, 1), pais_residencia="Colombia",
            telefono="3001234567",
        )
        db.add(cliente)
        await db.flush()
        ids = []
        for indice in range(sesiones):
            sesion_id = f"sesion-{indice}"
            db.add(SesionActivacionModel(
                id=sesion_id, cliente_id=cliente.id, installation_id=uuid.uuid4(), plataforma="ANDROID",
                modelo="Pixel", version_so="15", tipo_captura="FRAMES", estado="CREADA",
                creada_en=ahora, expira_en=ahora + timedelta(minutes=2),
            ))
            ids.append(sesion_id)
        await db.flush()
        for indice in range(rechazados_previos):
            db.add(IntentoPruebaVidaModel(
                cliente_id=cliente.id, sesion_id=ids[0], installation_id=uuid.uuid4(), estado="RECHAZADO",
                creado_en=ahora - timedelta(minutes=10 + indice),
            ))
        await db.commit()
        return cliente.id, ids


async def _verificar(factory, sesion_id: str, aprobado: bool):
    async with factory() as db:
        use_case = VerificarActivacionMovilUseCase(
            SqlAlchemyClienteRepository(db), SqlAlchemyActivacionMovilRepository(db),
            LivenessLento(aprobado), db.commit, rollback=db.rollback,
        )
        return await use_case.ejecutar("ana@example.com", sesion_id, "nonce", {}, {}, "corr")


async def test_dos_verificaciones_simultaneas_no_superan_el_limite(factory):
    cliente_id, sesiones = await _preparar(factory, rechazados_previos=2, sesiones=2)

    resultados = await asyncio.gather(
        *(_verificar(factory, sesion, aprobado=False) for sesion in sesiones), return_exceptions=True
    )

    agotados = [r for r in resultados if isinstance(r, IntentosActivacionAgotadosError)]
    assert len(agotados) == 1
    async with factory() as db:
        consumidos = await db.scalar(
            select(func.count()).select_from(IntentoPruebaVidaModel).where(
                IntentoPruebaVidaModel.cliente_id == cliente_id,
                IntentoPruebaVidaModel.estado.in_(["RECHAZADO", "EN_CURSO"]),
            )
        )
    assert consumidos == 3


async def test_dos_aprobaciones_simultaneas_dejan_un_solo_vinculo_activo(factory):
    cliente_id, sesiones = await _preparar(factory, rechazados_previos=0, sesiones=2)

    await asyncio.gather(*(_verificar(factory, sesion, aprobado=True) for sesion in sesiones), return_exceptions=True)

    async with factory() as db:
        activos = await db.scalar(
            select(func.count()).select_from(DispositivoVinculadoModel).where(
                DispositivoVinculadoModel.cliente_id == cliente_id,
                DispositivoVinculadoModel.estado == "ACTIVO",
            )
        )
    assert activos == 1
