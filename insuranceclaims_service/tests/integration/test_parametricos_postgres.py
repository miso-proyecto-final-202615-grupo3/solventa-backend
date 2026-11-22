"""HU4.2.3 · Dos consumidores paramétricos contra Postgres real: cada evento genera un solo siniestro.

Se salta sin `TEST_POSTGRES_URL` (dentro de la red de compose, con `scripts/sql/insuranceclaims_hu4_2_3.sql`
aplicado: `postgresql+asyncpg://postgres:postgres@db:5432/identity_db`).
"""
import asyncio
import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.core.database import Base
from src.domain.siniestros.entities import EventoExterno
from src.domain.siniestros.parametricos import PolizaParametrica
from src.infrastructure.messaging.procesador_eventos_parametricos import ProcesadorEventosParametricos
from src.infrastructure.persistence.models import EventoExternoModel, PolizaParametricaModel, SiniestroModel
from src.infrastructure.persistence.polizas_parametricas_repository_impl import SqlAlchemyPolizaParametricaRepository
from src.infrastructure.persistence.siniestros_repository_impl import SqlAlchemyEventoExternoRepository
from tests.fakes import AHORA, CLIENTE, PolizasFalsas, poliza

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")
pytestmark = [pytest.mark.postgres, pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL no está definida")]


class PolizasLentas(PolizasFalsas):
    async def obtener(self, poliza_id, cliente_id, correlation_id):
        await asyncio.sleep(0.05)
        return await super().obtener(poliza_id, cliente_id, correlation_id)


async def test_dos_consumidores_no_duplican_siniestros():
    engine = create_async_engine(POSTGRES_URL)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS insuranceclaims"))
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    zona = f"ZONA{uuid.uuid4().hex[:8].upper()}"
    p = poliza(poliza_id=uuid.uuid4(), producto_codigo="SEGURO_PARAMETRICO", numero=f"SLV-PG-{zona[-4:]}")
    eventos = [f"PG-{zona}-{i}" for i in range(4)]
    async with factory() as session:
        await SqlAlchemyPolizaParametricaRepository(session).guardar_o_actualizar(PolizaParametrica(
            poliza_id=p.poliza_id, cliente_id=CLIENTE, poliza_numero=p.numero, cobertura="LLUVIA_EXTREMA",
            indice=zona, umbral=Decimal("50"), monto_compensacion=Decimal("1000"), moneda="COP", actualizada_en=AHORA,
        ))
        repo = SqlAlchemyEventoExternoRepository(session)
        for indice, event_id in enumerate(eventos):
            await repo.guardar(EventoExterno(
                event_id=event_id, fuente="TEST", tipo="LLUVIA", checksum=event_id, ocurrido_en=AHORA,
                recibido_en=AHORA.replace(second=indice), payload_referencia="test",
                datos={"zona": zona, "precipitacion_mm": 60 + indice},
            ))
        await session.commit()
    polizas = PolizasLentas(p)

    def consumidor():
        return ProcesadorEventosParametricos(factory, polizas, lambda: AHORA, ["VIGENTE"], 0.01, 3)

    try:
        await asyncio.gather(consumidor().procesar_pendientes(), consumidor().procesar_pendientes())
        async with factory() as session:
            procesados = await session.scalar(
                select(func.count()).select_from(EventoExternoModel)
                .where(EventoExternoModel.event_id.in_(eventos), EventoExternoModel.estado == "PROCESADO")
            )
            siniestros = await session.scalar(
                select(func.count()).select_from(SiniestroModel).where(SiniestroModel.poliza_id == p.poliza_id)
            )
        assert (procesados, siniestros) == (4, 4)
    finally:
        async with factory() as session:
            await session.execute(text(
                "DELETE FROM insuranceclaims.evento_outbox WHERE agregado_id IN "
                "(SELECT siniestro_id FROM insuranceclaims.siniestro WHERE poliza_id = :p)"
            ), {"p": p.poliza_id})
            await session.execute(text(
                "DELETE FROM insuranceclaims.indemnizacion WHERE siniestro_id IN "
                "(SELECT siniestro_id FROM insuranceclaims.siniestro WHERE poliza_id = :p)"
            ), {"p": p.poliza_id})
            await session.execute(delete(SiniestroModel).where(SiniestroModel.poliza_id == p.poliza_id))
            await session.execute(text(
                "DELETE FROM insuranceclaims.activacion_poliza WHERE poliza_id = :p"
            ), {"p": p.poliza_id})
            await session.execute(text(
                "DELETE FROM insuranceclaims.activacion_parametrica WHERE clave_idempotencia LIKE :c"
            ), {"c": f"PARAM:PG-{zona}-%"})
            await session.execute(delete(EventoExternoModel).where(EventoExternoModel.event_id.in_(eventos)))
            await session.execute(delete(PolizaParametricaModel).where(PolizaParametricaModel.poliza_id == p.poliza_id))
            await session.commit()
        await engine.dispose()
