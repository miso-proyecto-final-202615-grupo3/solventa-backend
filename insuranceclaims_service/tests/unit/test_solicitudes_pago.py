"""HU4.2.3 · Solicitud de pago de la indemnización: el relay la entrega a Pagos y el adaptador SQS la publica."""
import json
import uuid
from types import SimpleNamespace

import boto3
import pytest
from botocore.stub import ANY, Stubber
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.core.database import Base
from src.domain.siniestros.entities import EventoOutbox, Siniestro
from src.infrastructure.messaging.outbox_relay import OutboxRelay
from src.infrastructure.pagos.solicitudes_pago import (
    RegistroSolicitudesPago,
    SqsSolicitudesPago,
    crear_solicitudes_pago,
)
from src.infrastructure.persistence.models import EventoOutboxModel
from src.infrastructure.persistence.siniestros_repository_impl import (
    SqlAlchemyEventoOutboxRepository,
    SqlAlchemySiniestroRepository,
)
from tests.fakes import AHORA, CLIENTE

COLA = "https://sqs.us-east-1.amazonaws.com/000000000000/pago-indemnizacion"


@pytest.fixture
async def factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False},
        execution_options={"schema_translate_map": {"insuranceclaims": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


class PagosFalsos:
    def __init__(self, fallos: int = 0) -> None:
        self.fallos = fallos
        self.solicitudes: list[dict] = []

    async def solicitar(self, solicitud, correlation_id):
        if self.fallos:
            self.fallos -= 1
            raise RuntimeError("SQS no respondió")
        self.solicitudes.append(solicitud)


async def _sembrar(factory) -> dict[str, uuid.UUID]:
    async with factory() as session:
        siniestro = Siniestro(
            poliza_id=uuid.uuid4(), tipo="LLUVIA_EXTREMA", estado="APROBADO", clave_idempotencia=str(uuid.uuid4()),
            ocurrido_en=AHORA, reportado_en=AHORA, cliente_id=CLIENTE, numero="SIN-2026-PARAM001",
        )
        await SqlAlchemySiniestroRepository(session).guardar(siniestro)
        outbox = SqlAlchemyEventoOutboxRepository(session)
        ids = {}
        for indice, tipo in enumerate(["SINIESTRO_ESTADO", "PAGO_INDEMNIZACION_SOLICITADO"]):
            evento = EventoOutbox(
                tipo=tipo, agregado_id=siniestro.siniestro_id, creado_en=AHORA.replace(second=indice),
                payload={"tipo": tipo, "estado": "APROBADO", "numero": "SIN-2026-PARAM001", "clave_idempotencia": "PAGO:X"},
            )
            await outbox.guardar(evento)
            ids[tipo] = evento.evento_id
        await session.commit()
    return ids


async def _estado(factory, evento_id):
    async with factory() as session:
        return (await session.get(EventoOutboxModel, evento_id)).estado


async def test_sin_notificaciones_solo_se_entregan_los_pagos(factory):
    ids = await _sembrar(factory)
    pagos = PagosFalsos()

    publicados = await OutboxRelay(factory, None, 0.01, 5, pagos=pagos).publicar_pendientes()

    assert publicados == 1
    assert pagos.solicitudes[0]["clave_idempotencia"] == "PAGO:X"
    assert await _estado(factory, ids["PAGO_INDEMNIZACION_SOLICITADO"]) == "PUBLICADO"
    assert await _estado(factory, ids["SINIESTRO_ESTADO"]) == "PENDIENTE"  # espera a que haya push


async def test_fallo_de_pagos_se_reintenta(factory):
    ids = await _sembrar(factory)
    relay = OutboxRelay(factory, None, 0.01, 5, pagos=PagosFalsos(fallos=1))

    assert await relay.publicar_pendientes() == 0
    assert await relay.publicar_pendientes() == 1
    assert await _estado(factory, ids["PAGO_INDEMNIZACION_SOLICITADO"]) == "PUBLICADO"


async def test_sqs_publica_la_solicitud_con_su_tipo():
    client = boto3.client("sqs", region_name="us-east-1", aws_access_key_id="x", aws_secret_access_key="x")
    solicitud = {"tipo": "PAGO_INDEMNIZACION_SOLICITADO", "numero": "SIN-2026-PARAM001", "monto": "300000.00"}
    with Stubber(client) as stub:
        stub.add_response(
            "send_message", {"MessageId": "m-1"},
            {"QueueUrl": COLA, "MessageBody": json.dumps(solicitud, separators=(",", ":")), "MessageAttributes": ANY},
        )
        await SqsSolicitudesPago(COLA, "us-east-1", client=client).solicitar(solicitud, "corr-1")
        stub.assert_no_pending_responses()


async def test_fabrica_de_solicitudes_de_pago():
    assert isinstance(crear_solicitudes_pago(SimpleNamespace(SOLICITUDES_PAGO="registro")), RegistroSolicitudesPago)
    with pytest.raises(ValueError):
        crear_solicitudes_pago(SimpleNamespace(SOLICITUDES_PAGO="sqs", PAGO_INDEMNIZACION_QUEUE_URL="", AWS_REGION="us-east-1", SQS_ENDPOINT_URL=""))
    with pytest.raises(ValueError):
        crear_solicitudes_pago(SimpleNamespace(SOLICITUDES_PAGO="kafka"))
