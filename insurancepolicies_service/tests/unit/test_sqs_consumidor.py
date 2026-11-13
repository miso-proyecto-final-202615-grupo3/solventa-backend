import asyncio
import json

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from src.infrastructure.messaging.sqs_consumidor import ConsumidorSqs
from src.infrastructure.messaging.sqs_publicador import crear_cliente_sqs

QUEUE = "solventa-pago-aprobado"


@pytest.fixture
def sqs(monkeypatch):
    for variable in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(variable, "test")
    with mock_aws():
        cliente = boto3.client("sqs", region_name="us-east-1")
        url = cliente.create_queue(QueueName=QUEUE)["QueueUrl"]
        yield cliente, url


def consumidor(cliente, url, manejador, **kwargs):
    kwargs.setdefault("espera_segundos", 0)
    kwargs.setdefault("visibilidad_segundos", 1)
    return ConsumidorSqs("prueba", url, manejador, client=cliente, **kwargs)


def pendientes(cliente, url) -> int:
    atributos = cliente.get_queue_attributes(QueueUrl=url, AttributeNames=["All"])["Attributes"]
    return int(atributos["ApproximateNumberOfMessages"]) + int(
        atributos["ApproximateNumberOfMessagesNotVisible"]
    )


async def test_entrega_el_payload_al_manejador_y_borra_el_mensaje(sqs):
    cliente, url = sqs
    recibidos = []

    async def manejador(payload):
        recibidos.append(payload)

    cliente.send_message(QueueUrl=url, MessageBody=json.dumps({"tipo": "PagoAprobado", "n": 1}))

    assert await consumidor(cliente, url, manejador).procesar_lote() == 1

    assert recibidos == [{"tipo": "PagoAprobado", "n": 1}]
    assert pendientes(cliente, url) == 0


async def test_procesa_varios_mensajes_por_lectura(sqs):
    cliente, url = sqs
    recibidos = []

    async def manejador(payload):
        recibidos.append(payload["n"])

    for n in range(3):
        cliente.send_message(QueueUrl=url, MessageBody=json.dumps({"n": n}))

    assert await consumidor(cliente, url, manejador, max_mensajes=10).procesar_lote() == 3

    assert sorted(recibidos) == [0, 1, 2] and pendientes(cliente, url) == 0


async def test_si_el_manejador_falla_el_mensaje_no_se_borra_y_se_reentrega(sqs):
    cliente, url = sqs
    intentos = []

    async def manejador(payload):
        intentos.append(payload)
        if len(intentos) == 1:
            raise RuntimeError("falla transitoria")

    cliente.send_message(QueueUrl=url, MessageBody=json.dumps({"n": 1}))
    c = consumidor(cliente, url, manejador, visibilidad_segundos=1)

    assert await c.procesar_lote() == 0
    assert pendientes(cliente, url) == 1
    await asyncio.sleep(1.2)  # vence el tiempo de visibilidad
    assert await c.procesar_lote() == 1

    assert len(intentos) == 2 and pendientes(cliente, url) == 0


async def test_un_mensaje_que_no_es_json_queda_en_la_cola_para_la_dlq(sqs):
    cliente, url = sqs
    llamadas = []

    async def manejador(payload):
        llamadas.append(payload)

    cliente.send_message(QueueUrl=url, MessageBody="esto no es json")

    assert await consumidor(cliente, url, manejador).procesar_lote() == 0

    assert llamadas == [] and pendientes(cliente, url) == 1


async def test_un_mensaje_defectuoso_no_impide_procesar_los_demas(sqs):
    cliente, url = sqs
    procesados = []

    async def manejador(payload):
        if payload["n"] == 1:
            raise ValueError("mensaje inválido")
        procesados.append(payload["n"])

    for n in range(3):
        cliente.send_message(QueueUrl=url, MessageBody=json.dumps({"n": n}))

    assert await consumidor(cliente, url, manejador, max_mensajes=10).procesar_lote() == 2

    assert sorted(procesados) == [0, 2] and pendientes(cliente, url) == 1


async def test_el_fallo_al_borrar_no_detiene_el_lote(sqs):
    cliente, url = sqs

    async def manejador(payload):
        pass

    class ClienteQueNoBorra:
        def __getattr__(self, nombre):
            return getattr(cliente, nombre)

        def delete_message(self, **kwargs):
            raise ClientError({"Error": {"Code": "ServiceUnavailable", "Message": "x"}}, "DeleteMessage")

    cliente.send_message(QueueUrl=url, MessageBody=json.dumps({"n": 1}))

    assert await consumidor(ClienteQueNoBorra(), url, manejador).procesar_lote() == 0


async def test_la_cancelacion_se_propaga_y_no_se_traga(sqs):
    cliente, url = sqs

    async def manejador(payload):
        raise asyncio.CancelledError

    cliente.send_message(QueueUrl=url, MessageBody=json.dumps({"n": 1}))

    with pytest.raises(asyncio.CancelledError):
        await consumidor(cliente, url, manejador).procesar_lote()


async def test_el_ciclo_sobrevive_a_errores_de_lectura_y_sigue_consumiendo(sqs):
    cliente, url = sqs
    recibidos = []
    lecturas = []

    class ClienteInestable:
        def __getattr__(self, nombre):
            return getattr(cliente, nombre)

        def receive_message(self, **kwargs):
            lecturas.append(1)
            if len(lecturas) == 1:
                raise ClientError({"Error": {"Code": "ServiceUnavailable", "Message": "x"}}, "ReceiveMessage")
            return cliente.receive_message(**kwargs)

    async def manejador(payload):
        recibidos.append(payload["n"])

    cliente.send_message(QueueUrl=url, MessageBody=json.dumps({"n": 7}))
    tarea = asyncio.create_task(
        consumidor(ClienteInestable(), url, manejador, pausa_error_segundos=0.01).ejecutar()
    )
    for _ in range(100):
        if recibidos:
            break
        await asyncio.sleep(0.02)
    tarea.cancel()
    with pytest.raises(asyncio.CancelledError):
        await tarea

    assert recibidos == [7] and len(lecturas) >= 2


async def test_cancelar_el_ciclo_con_una_lectura_en_curso_no_espera_al_long_polling(sqs):
    cliente, url = sqs

    class ClienteLento:
        def __getattr__(self, nombre):
            return getattr(cliente, nombre)

        def receive_message(self, **kwargs):
            import time

            time.sleep(1.5)
            return {}

    async def manejador(payload):
        pass

    tarea = asyncio.create_task(consumidor(ClienteLento(), url, manejador).ejecutar())
    await asyncio.sleep(0.1)
    inicio = asyncio.get_running_loop().time()
    tarea.cancel()
    with pytest.raises(asyncio.CancelledError):
        await tarea

    assert asyncio.get_running_loop().time() - inicio < 1.0


async def test_usa_los_parametros_de_long_polling_configurados(sqs):
    cliente, url = sqs
    parametros = {}

    class ClienteEspia:
        def __getattr__(self, nombre):
            return getattr(cliente, nombre)

        def receive_message(self, **kwargs):
            parametros.update(kwargs)
            return {}

    async def manejador(payload):
        pass

    await consumidor(
        ClienteEspia(), url, manejador, espera_segundos=20, max_mensajes=4, visibilidad_segundos=90
    ).procesar_lote()

    assert parametros["WaitTimeSeconds"] == 20
    assert parametros["MaxNumberOfMessages"] == 4
    assert parametros["VisibilityTimeout"] == 90
    assert parametros["QueueUrl"] == url


def test_el_cliente_sqs_usa_endpoint_de_localstack_solo_si_se_configura(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")

    local = crear_cliente_sqs("http://localstack:4566", "us-east-1")
    remoto = crear_cliente_sqs("", "us-east-1")

    assert local.meta.endpoint_url == "http://localstack:4566"
    assert "localstack" not in remoto.meta.endpoint_url
    assert remoto.meta.endpoint_url.endswith("amazonaws.com")
