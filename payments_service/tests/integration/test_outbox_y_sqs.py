import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import boto3
import pytest
from moto import mock_aws
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.publicador_eventos import PublicacionEventoError, PublicadorEventos
from src.domain.eventos.entities import EstadoEvento, EventoOutbox
from src.infrastructure.messaging.outbox_relay import OutboxRelay
from src.infrastructure.messaging.sqs_publicador import SqsPublicadorEventos
from src.infrastructure.persistence.evento_outbox_repository_impl import (
    SqlAlchemyEventoOutboxRepository,
)
from src.infrastructure.persistence.models import EventoOutboxModel

AHORA = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)


def evento(minutos: int = 0, **payload) -> EventoOutbox:
    return EventoOutbox(
        tipo="PagoAprobado",
        agregado_id=uuid.uuid4(),
        payload={"datos": payload or {"n": minutos}},
        creado_en=AHORA + timedelta(minutes=minutos),
    )


async def test_el_evento_forma_parte_de_la_transaccion(db_session: AsyncSession):
    repo = SqlAlchemyEventoOutboxRepository(db_session)
    await repo.agregar(evento())

    await db_session.rollback()

    assert await repo.obtener_pendientes(10) == []


async def test_obtiene_pendientes_en_orden_de_creacion_y_respeta_el_limite(db_session: AsyncSession):
    repo = SqlAlchemyEventoOutboxRepository(db_session)
    segundo, primero, tercero = evento(2), evento(1), evento(3)
    for e in (segundo, primero, tercero):
        await repo.agregar(e)
    await db_session.commit()

    pendientes = await repo.obtener_pendientes(2)

    assert [e.evento_id for e in pendientes] == [primero.evento_id, segundo.evento_id]
    assert pendientes[0].payload == primero.payload and pendientes[0].estado == EstadoEvento.PENDIENTE


async def test_marcar_publicado_y_registrar_fallo(db_session: AsyncSession):
    repo = SqlAlchemyEventoOutboxRepository(db_session)
    publicado, fallido = evento(1), evento(2)
    await repo.agregar(publicado)
    await repo.agregar(fallido)
    await repo.registrar_fallo(fallido.evento_id, "x" * 600)
    await repo.marcar_publicado(publicado.evento_id, AHORA)
    await db_session.commit()

    pendientes = await repo.obtener_pendientes(10)

    assert [e.evento_id for e in pendientes] == [fallido.evento_id]
    assert (pendientes[0].intentos, len(pendientes[0].ultimo_error)) == (1, 500)
    fila = (
        await db_session.execute(
            select(EventoOutboxModel).where(EventoOutboxModel.evento_id == publicado.evento_id)
        )
    ).scalar_one()
    assert (fila.estado, fila.intentos, fila.ultimo_error) == ("PUBLICADO", 1, None)
    assert fila.publicado_en is not None


class PublicadorFalso(PublicadorEventos):
    def __init__(self, fallar_en: int | None = None) -> None:
        self.fallar_en = fallar_en
        self.publicados: list[tuple[str, dict]] = []

    async def publicar(self, tipo, payload):
        if self.fallar_en is not None and len(self.publicados) == self.fallar_en:
            raise PublicacionEventoError("bus caído")
        self.publicados.append((tipo, payload))


@pytest.fixture
def fabrica(db_session: AsyncSession):
    # El relay abre su propia sesión; en la prueba reutiliza la misma base en memoria.
    class Fabrica:
        def __call__(self):
            return _Sesion(db_session)

    return Fabrica()


@pytest.fixture
def bloqueo_simulado(monkeypatch):
    bloqueo = AsyncMock()
    monkeypatch.setattr(OutboxRelay, "_adquirir_bloqueo", bloqueo)
    return bloqueo


class _Sesion:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        return False


async def test_el_relay_publica_los_pendientes_una_sola_vez(
    db_session: AsyncSession, fabrica, bloqueo_simulado
):
    repo = SqlAlchemyEventoOutboxRepository(db_session)
    uno, dos = evento(1), evento(2)
    await repo.agregar(uno)
    await repo.agregar(dos)
    await db_session.commit()
    publicador = PublicadorFalso()
    relay = OutboxRelay(fabrica, publicador, 0.01, 10)

    assert await relay.publicar_pendientes() == 2
    assert await relay.publicar_pendientes() == 0
    assert bloqueo_simulado.await_count == 4

    assert publicador.publicados == [("PagoAprobado", uno.payload), ("PagoAprobado", dos.payload)]
    assert await repo.obtener_pendientes(10) == []


async def test_el_relay_se_detiene_en_el_primer_fallo_y_reintenta_despues(
    db_session: AsyncSession, fabrica, bloqueo_simulado
):
    repo = SqlAlchemyEventoOutboxRepository(db_session)
    uno, dos, tres = evento(1), evento(2), evento(3)
    for e in (uno, dos, tres):
        await repo.agregar(e)
    await db_session.commit()
    publicador = PublicadorFalso(fallar_en=1)
    relay = OutboxRelay(fabrica, publicador, 0.01, 10)

    assert await relay.publicar_pendientes() == 1
    pendientes = await repo.obtener_pendientes(10)
    assert [e.evento_id for e in pendientes] == [dos.evento_id, tres.evento_id]
    assert (pendientes[0].intentos, pendientes[0].ultimo_error) == (1, "bus caído")

    publicador.fallar_en = None
    assert await relay.publicar_pendientes() == 2
    assert [p[1] for p in publicador.publicados] == [uno.payload, dos.payload, tres.payload]
    assert bloqueo_simulado.await_count == 5


async def test_el_relay_solicita_el_bloqueo_transaccional_postgresql(fabrica):
    session = AsyncMock(spec=AsyncSession)
    relay = OutboxRelay(fabrica, PublicadorFalso(), 0.01, 10)

    await relay._adquirir_bloqueo(session)

    statement, parametros = session.execute.await_args.args
    assert str(statement) == "SELECT pg_advisory_xact_lock(:lock_key)"
    assert parametros == {"lock_key": 0x534F4C564F555442}


async def test_el_relay_no_publica_si_falla_el_bloqueo(
    db_session: AsyncSession, fabrica, monkeypatch
):
    repo = SqlAlchemyEventoOutboxRepository(db_session)
    pendiente = evento()
    await repo.agregar(pendiente)
    await db_session.commit()
    monkeypatch.setattr(OutboxRelay, "_adquirir_bloqueo", AsyncMock(side_effect=RuntimeError("db")))
    publicador = PublicadorFalso()
    relay = OutboxRelay(fabrica, publicador, 0.01, 10)

    with pytest.raises(RuntimeError, match="db"):
        await relay.publicar_pendientes()

    assert publicador.publicados == []
    assert [e.evento_id for e in await repo.obtener_pendientes(10)] == [pendiente.evento_id]


async def test_el_ciclo_del_relay_sobrevive_a_errores_inesperados(fabrica):
    import asyncio

    llamadas = 0

    class Relay(OutboxRelay):
        async def publicar_pendientes(self):
            nonlocal llamadas
            llamadas += 1
            if llamadas == 1:
                raise RuntimeError("falla de base de datos")
            return 0

    tarea = asyncio.create_task(Relay(fabrica, PublicadorFalso(), 0.01, 10).ejecutar())
    await asyncio.sleep(0.1)
    tarea.cancel()
    with pytest.raises(asyncio.CancelledError):
        await tarea

    assert llamadas >= 2


QUEUE = "solventa-pago-aprobado"


@pytest.fixture
def sqs(monkeypatch):
    for variable in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(variable, "test")
    with mock_aws():
        cliente = boto3.client("sqs", region_name="us-east-1")
        url = cliente.create_queue(QueueName=QUEUE)["QueueUrl"]
        yield cliente, url


async def test_publica_el_mensaje_en_sqs(sqs):
    cliente, url = sqs
    payload = {"tipo": "PagoAprobado", "datos": {"monto": "1250000.50", "pago_id": str(uuid.uuid4())}}

    await SqsPublicadorEventos(queue_url=url, endpoint_url="", region_name="us-east-1").publicar(
        "PagoAprobado", payload
    )

    (mensaje,) = cliente.receive_message(QueueUrl=url, MessageAttributeNames=["All"])["Messages"]
    assert json.loads(mensaje["Body"]) == payload
    assert mensaje["MessageAttributes"]["tipo"]["StringValue"] == "PagoAprobado"


async def test_error_de_sqs_se_traduce(sqs):
    _, url = sqs
    inexistente = url.replace(QUEUE, "no-existe")

    with pytest.raises(PublicacionEventoError):
        await SqsPublicadorEventos(
            queue_url=inexistente, endpoint_url="", region_name="us-east-1"
        ).publicar("PagoAprobado", {})


async def test_sin_cola_configurada_falla(sqs):
    with pytest.raises(PublicacionEventoError, match="no está configurada"):
        await SqsPublicadorEventos(queue_url="", endpoint_url="", region_name="us-east-1").publicar(
            "PagoAprobado", {}
        )


def test_el_endpoint_de_localstack_se_pasa_a_boto3(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")

    publicador = SqsPublicadorEventos(
        queue_url="http://localstack:4566/000000000000/q",
        endpoint_url="http://localstack:4566",
        region_name="us-east-1",
    )

    assert publicador._client.meta.endpoint_url == "http://localstack:4566"
