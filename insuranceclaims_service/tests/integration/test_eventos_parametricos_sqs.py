"""HU4.2.3 · Bus SQS (diseño HA8): ingesta → cola → consumidor → siniestro; duplicados, reintentos y DLQ."""
import json
import uuid
from datetime import UTC, datetime

import pytest
from botocore.exceptions import ClientError
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.core.config import settings
from src.core.database import Base
from src.infrastructure.messaging.sqs_eventos_parametricos import (
    ConsumidorSqsEventosParametricos,
    SqsBusEventosParametricos,
)
from src.infrastructure.persistence.models import EventoExternoModel, SiniestroModel
from src.main import app
from src.presentation.dependencies import get_bus_eventos, get_db, get_polizas_port, get_reloj
from tests.fakes import PolizasFalsas, poliza

BASE = "/api/v1/insuranceclaims-service"
FUENTE = {"X-Fuente-Token": "token-fuente-de-prueba"}
OPERADOR = {"X-Operador-Token": "token-operador-de-prueba"}
AHORA = datetime(2026, 11, 21, 20, 0, tzinfo=UTC)
COLA, DLQ = "https://sqs.local/eventos", "https://sqs.local/eventos-dlq"
PARAMETRICA = poliza(producto_codigo="SEGURO_PARAMETRICO", numero="SLV-PARAM-1")


class SqsFalso:
    """Lo mínimo de SQS: mensajes visibles/en vuelo, conteo de recepciones y borrado por ReceiptHandle."""

    def __init__(self, caido: bool = False) -> None:
        self.colas: dict[str, list[dict]] = {COLA: [], DLQ: []}
        self.caido = caido

    def send_message(self, QueueUrl, MessageBody, MessageAttributes=None):
        if self.caido:
            raise ClientError({"Error": {"Code": "ServiceUnavailable", "Message": "caído"}}, "SendMessage")
        self.colas[QueueUrl].append({"Body": MessageBody, "recibido": 0, "visible": True, "atributos": MessageAttributes})
        return {"MessageId": str(uuid.uuid4())}

    def receive_message(self, QueueUrl, MaxNumberOfMessages=10, **_):
        entregados = []
        for mensaje in self.colas[QueueUrl]:
            if mensaje["visible"] and len(entregados) < MaxNumberOfMessages:
                mensaje["visible"] = False
                mensaje["recibido"] += 1
                mensaje["ReceiptHandle"] = str(uuid.uuid4())
                entregados.append({"Body": mensaje["Body"], "ReceiptHandle": mensaje["ReceiptHandle"],
                                   "Attributes": {"ApproximateReceiveCount": str(mensaje["recibido"])}})
        return {"Messages": entregados}

    def delete_message(self, QueueUrl, ReceiptHandle):
        self.colas[QueueUrl] = [m for m in self.colas[QueueUrl] if m.get("ReceiptHandle") != ReceiptHandle]

    def vence_visibilidad(self):
        for mensaje in self.colas[COLA]:
            mensaje["visible"] = True


def _evento(event_id="IDEAM-BOG-SQS-1", mm=72.5) -> dict:
    return {"event_id": event_id, "fuente": "IDEAM", "tipo": "LLUVIA", "ocurrido_en": "2026-11-21T10:00:00-05:00",
            "datos": {"zona": "BOGOTA", "precipitacion_mm": mm}}


@pytest.fixture
async def entorno(monkeypatch):
    monkeypatch.setattr(settings, "EVENTOS_FUENTE_TOKEN", FUENTE["X-Fuente-Token"])
    monkeypatch.setattr(settings, "OPERADOR_TOKEN", OPERADOR["X-Operador-Token"])
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False},
        execution_options={"schema_translate_map": {"insuranceclaims": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    sqs = SqsFalso()
    polizas = PolizasFalsas(PARAMETRICA)

    async def db_override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_polizas_port] = lambda: polizas
    app.dependency_overrides[get_reloj] = lambda: (lambda: AHORA)
    app.dependency_overrides[get_bus_eventos] = lambda: SqsBusEventosParametricos(COLA, sqs)
    consumidor = ConsumidorSqsEventosParametricos(
        factory, polizas, lambda: AHORA, ["VIGENTE"], 0.01, 3, client=sqs, queue_url=COLA, dlq_url=DLQ, espera_segundos=0,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.put(
            f"{BASE}/polizas-parametricas/{PARAMETRICA.poliza_id}", headers=OPERADOR,
            json={"cliente_id": str(PARAMETRICA.cliente_id), "cobertura": "LLUVIA_EXTREMA", "indice": "BOGOTA",
                  "monto_compensacion": 300000},
        )
        yield client, factory, consumidor, sqs, polizas
    app.dependency_overrides.clear()
    await engine.dispose()


async def _contar(factory, modelo) -> int:
    async with factory() as session:
        return await session.scalar(select(func.count()).select_from(modelo))


async def test_el_evento_pasa_por_la_cola_y_crea_el_siniestro(entorno):
    client, factory, consumidor, sqs, _ = entorno

    respuesta = await client.post(f"{BASE}/eventos-parametricos", json=_evento(), headers=FUENTE)

    assert respuesta.status_code == 202 and respuesta.json()["estado"] == "ENCOLADO"
    assert len(sqs.colas[COLA]) == 1 and json.loads(sqs.colas[COLA][0]["Body"])["checksum"]
    assert await _contar(factory, EventoExternoModel) == 0  # aún no se consume

    assert await consumidor.procesar_pendientes() == 1

    assert sqs.colas[COLA] == []  # se borra solo después de procesar
    assert await _contar(factory, SiniestroModel) == 1
    traza = (await client.get(f"{BASE}/eventos-parametricos/IDEAM-BOG-SQS-1", headers=FUENTE)).json()
    assert traza["estado"] == "PROCESADO" and traza["resultado"][0]["resultado"] == "ACTIVADA"
    repetido = await client.post(f"{BASE}/eventos-parametricos", json=_evento(), headers=FUENTE)
    assert repetido.status_code == 200 and sqs.colas[COLA] == []  # ya procesado: no se vuelve a encolar


async def test_mensaje_duplicado_genera_un_solo_siniestro(entorno):
    client, factory, consumidor, sqs, _ = entorno
    await client.post(f"{BASE}/eventos-parametricos", json=_evento(), headers=FUENTE)
    sqs.colas[COLA].append(dict(sqs.colas[COLA][0]))  # entrega al menos una vez

    await consumidor.procesar_pendientes()

    assert sqs.colas[COLA] == []
    assert await _contar(factory, SiniestroModel) == 1


async def test_error_transitorio_deja_el_mensaje_en_la_cola(entorno):
    client, factory, consumidor, sqs, polizas = entorno
    await client.post(f"{BASE}/eventos-parametricos", json=_evento(), headers=FUENTE)
    polizas.caido = True

    assert await consumidor.procesar_pendientes() == 0
    assert len(sqs.colas[COLA]) == 1  # SQS lo reentrega al vencer la visibilidad

    sqs.vence_visibilidad()
    polizas.caido = False
    assert await consumidor.procesar_pendientes() == 1
    assert await _contar(factory, SiniestroModel) == 1
    async with factory() as session:
        evento = await session.scalar(select(EventoExternoModel))
    assert (evento.estado, evento.intentos) == ("PROCESADO", 1)


async def test_mensaje_ilegible_va_a_la_dlq(entorno):
    _, factory, consumidor, sqs, _ = entorno
    sqs.send_message(COLA, "{no es json")

    await consumidor.procesar_pendientes()

    assert sqs.colas[COLA] == [] and len(sqs.colas[DLQ]) == 1
    assert await _contar(factory, EventoExternoModel) == 0


async def test_sin_sqs_la_fuente_recibe_503_y_reintenta(entorno):
    client, _, _, sqs, _ = entorno
    sqs.caido = True

    respuesta = await client.post(f"{BASE}/eventos-parametricos", json=_evento(), headers=FUENTE)

    assert respuesta.status_code == 503
