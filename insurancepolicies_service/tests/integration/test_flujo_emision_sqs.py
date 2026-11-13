"""Flujo completo con SQS simulado (moto): PagoAprobado -> póliza -> outbox -> PolizaEmitida -> PDF."""
import asyncio
import hashlib
import json
import uuid
from collections.abc import AsyncGenerator
from datetime import timedelta
from zoneinfo import ZoneInfo

import boto3
import pytest
from emision_fakes import (
    CLIENTE_ID,
    COTIZACION_ID,
    PRODUCTO_ID,
    CotizacionesFalsas,
    GeneradorFalso,
    TitularesFalsos,
    firma,
)
from httpx import ASGITransport, AsyncClient
from moto import mock_aws
from pdf_utils import paginas_pdf, png, requiere_weasyprint, texto_pdf
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.application.ports.generador_pdf import GeneracionPdfError
from src.domain.certificados.entities import EstadoGeneracion
from src.domain.eventos.entities import EstadoEvento
from src.domain.firmas.entities import ArchivoFirma, EstadoFirma
from src.domain.polizas.entities import EstadoCertificado
from src.infrastructure.messaging.outbox_relay import OutboxRelay
from src.infrastructure.messaging.sqs_consumidor import ConsumidorSqs
from src.infrastructure.messaging.sqs_publicador import SqsPublicadorEventos
from src.infrastructure.pdf.generador_certificado import GeneradorCertificadoWeasyPrint
from src.infrastructure.persistence.firma_digital_repository_impl import (
    SqlAlchemyFirmaDigitalRepository,
)
from src.infrastructure.persistence.models import (
    EventoOutboxModel,
    GeneracionCertificadoModel,
    PolizaModel,
)
from src.infrastructure.persistence.poliza_repository_impl import SqlAlchemyPolizaRepository
from src.infrastructure.storage.certificado_local_repository import (
    LocalAlmacenamientoCertificadoRepository,
)
from src.infrastructure.storage.firma_local_repository import LocalAlmacenamientoFirmaRepository
from src.main import app
from src.presentation.consumers.handlers import ManejadorPagoAprobado, ManejadorPolizaEmitida
from src.presentation.dependencies import get_almacenamiento_certificado_repository, get_db

PAGO_APROBADO = "solventa-pago-aprobado"
POLIZA_EMITIDA = "solventa-poliza-emitida"
FIRMA_PNG = png()
HEADERS = {"X-Client-Id": str(CLIENTE_ID)}


def mensaje_pago_aprobado(**datos) -> dict:
    """Mensaje exactamente como lo publica payments_service."""
    return {
        "evento_id": str(uuid.uuid4()),
        "tipo": "PagoAprobado",
        "version": 1,
        "ocurrido_en": "2026-11-13T14:00:00+00:00",
        "correlation_id": "corr-e2e",
        "datos": {
            "pago_id": str(uuid.uuid4()),
            "cotizacion_id": str(COTIZACION_ID),
            "cliente_id": str(CLIENTE_ID),
            "monto": "1416100.00",
            "moneda": "COP",
            "metodo_pago": "PAYPAL",
            "proveedor_referencia": "PAYPAL_1",
            **datos,
        },
    }


class Entorno:
    def __init__(self, sqs, session_factory, tmp_path, generador) -> None:
        self.sqs = sqs
        self.session_factory = session_factory
        self.url_pago = sqs.get_queue_url(QueueName=PAGO_APROBADO)["QueueUrl"]
        self.url_poliza = sqs.get_queue_url(QueueName=POLIZA_EMITIDA)["QueueUrl"]
        self.almacenamiento_firmas = LocalAlmacenamientoFirmaRepository(tmp_path / "firmas")
        self.almacenamiento_certificados = LocalAlmacenamientoCertificadoRepository(tmp_path / "certs")
        (tmp_path / "firmas").mkdir()
        (tmp_path / "certs").mkdir()
        self.generador = generador
        self.cotizaciones = CotizacionesFalsas()
        self.titulares = TitularesFalsos()
        self.consumidor_pagos = ConsumidorSqs(
            "pago-aprobado",
            self.url_pago,
            ManejadorPagoAprobado(
                session_factory, lambda: self.cotizaciones, lambda: self.titulares
            ),
            client=sqs,
            espera_segundos=0,
            visibilidad_segundos=1,
        )
        self.relay = OutboxRelay(
            session_factory,
            SqsPublicadorEventos(queue_url=self.url_poliza, client=sqs),
            0.01,
            10,
        )
        # SQLite no tiene pg_advisory_xact_lock; el bloqueo se prueba contra PostgreSQL aparte.
        async def sin_bloqueo(session) -> None:
            return None

        self.relay._adquirir_bloqueo = sin_bloqueo
        self.consumidor_certificados = ConsumidorSqs(
            "poliza-emitida",
            self.url_poliza,
            ManejadorPolizaEmitida(
                session_factory,
                self.almacenamiento_firmas,
                self.almacenamiento_certificados,
                generador,
                ZoneInfo("America/Bogota"),
                timedelta(minutes=5),
            ),
            client=sqs,
            espera_segundos=0,
            visibilidad_segundos=1,
        )

    async def capturar_firma(self) -> None:
        capturada = firma(
            ruta_imagen=f"firma-digital/{CLIENTE_ID}/{uuid.uuid4()}/firma.png",
            firma_hash=hashlib.sha256(FIRMA_PNG).hexdigest(),
            tamano_bytes=len(FIRMA_PNG),
        )
        await self.almacenamiento_firmas.guardar(capturada.ruta_imagen, ArchivoFirma(FIRMA_PNG, "image/png"))
        async with self.session_factory() as session:
            await SqlAlchemyFirmaDigitalRepository(session).crear(capturada)
            await session.commit()

    def enviar_pago_aprobado(self, mensaje: dict | None = None) -> dict:
        mensaje = mensaje or mensaje_pago_aprobado()
        self.sqs.send_message(QueueUrl=self.url_pago, MessageBody=json.dumps(mensaje))
        return mensaje

    def mensajes(self, url: str) -> int:
        atributos = self.sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["All"])["Attributes"]
        return int(atributos["ApproximateNumberOfMessages"]) + int(
            atributos["ApproximateNumberOfMessagesNotVisible"]
        )

    async def polizas(self):
        async with self.session_factory() as session:
            return (await session.execute(select(PolizaModel))).scalars().all()

    async def eventos(self):
        async with self.session_factory() as session:
            return (await session.execute(select(EventoOutboxModel))).scalars().all()

    async def generaciones(self):
        async with self.session_factory() as session:
            return (
                await session.execute(
                    select(GeneracionCertificadoModel).order_by(GeneracionCertificadoModel.iniciada_en)
                )
            ).scalars().all()


@pytest.fixture
def sqs(monkeypatch):
    for variable in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(variable, "test")
    with mock_aws():
        cliente = boto3.client("sqs", region_name="us-east-1")
        cliente.create_queue(QueueName=PAGO_APROBADO)
        cliente.create_queue(QueueName=POLIZA_EMITIDA)
        yield cliente


@pytest.fixture(params=[pytest.param("real", marks=requiere_weasyprint), "falso"])
def generador(request):
    return GeneradorCertificadoWeasyPrint() if request.param == "real" else GeneradorFalso(b"%PDF-1.7 falso")


@pytest.fixture
def entorno(sqs, session_factory: async_sessionmaker, tmp_path, generador) -> Entorno:
    return Entorno(sqs, session_factory, tmp_path, generador)


@pytest.fixture
def entorno_falso(sqs, session_factory: async_sessionmaker, tmp_path) -> Entorno:
    return Entorno(sqs, session_factory, tmp_path, GeneradorFalso(b"%PDF-1.7 falso"))


@pytest.fixture
async def client(entorno) -> AsyncGenerator[AsyncClient, None]:
    async def _db():
        async with entorno.session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_almacenamiento_certificado_repository] = (
        lambda: entorno.almacenamiento_certificados
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def test_del_pago_aprobado_al_certificado_descargable(entorno, client):
    await entorno.capturar_firma()
    entorno.enviar_pago_aprobado()

    # 1. PagoAprobado -> póliza emitida y PolizaEmitida en el outbox
    assert await entorno.consumidor_pagos.procesar_lote() == 1
    assert entorno.mensajes(entorno.url_pago) == 0
    (poliza,) = await entorno.polizas()
    assert poliza.estado == "EMITIDA" and poliza.estado_certificado == "PENDIENTE"
    assert poliza.ruta_certificado is None and poliza.cotizacion_id == COTIZACION_ID
    assert poliza.producto_id == PRODUCTO_ID
    (evento,) = await entorno.eventos()
    assert (evento.tipo, evento.estado, evento.agregado_id) == ("PolizaEmitida", "PENDIENTE", poliza.poliza_id)
    resumen = await client.get(
        f"/api/v1/insurancepolicies-service/cotizaciones/{COTIZACION_ID}/poliza", headers=HEADERS
    )
    assert resumen.status_code == 200 and resumen.json()["estado_certificado"] == "PENDIENTE"
    aun_no = await client.get(
        f"/api/v1/insurancepolicies-service/polizas/{poliza.poliza_id}/certificado/descarga", headers=HEADERS
    )
    assert aun_no.status_code == 409

    # 2. Outbox relay -> cola PolizaEmitida
    assert await entorno.relay.publicar_pendientes() == 1
    assert await entorno.relay.publicar_pendientes() == 0
    assert entorno.mensajes(entorno.url_poliza) == 1
    assert (await entorno.eventos())[0].estado == EstadoEvento.PUBLICADO.value

    # 3. PolizaEmitida -> certificado PDF
    assert await entorno.consumidor_certificados.procesar_lote() == 1
    assert entorno.mensajes(entorno.url_poliza) == 0

    (poliza,) = await entorno.polizas()
    ruta = f"certificados-poliza/{CLIENTE_ID}/{poliza.poliza_id}/certificado-poliza.pdf"
    assert poliza.estado_certificado == "GENERADO" and poliza.ruta_certificado == ruta
    assert (entorno.almacenamiento_certificados.directorio_base / ruta).read_bytes().startswith(b"%PDF-")
    (generacion,) = await entorno.generaciones()
    assert generacion.estado == EstadoGeneracion.GENERADO.value
    assert generacion.ruta_certificado == ruta and generacion.finalizada_en is not None
    assert generacion.plantilla == "certificado_poliza.html"
    assert generacion.datos_plantilla["poliza"]["numero"] == poliza.numero
    assert generacion.datos_plantilla["firma"]["capturada_en"] == "2026-11-12"
    async with entorno.session_factory() as session:
        vinculada = await SqlAlchemyFirmaDigitalRepository(session).obtener_por_poliza(poliza.poliza_id)
    assert vinculada.estado == EstadoFirma.VINCULADA

    # 4. Consulta de estado y descarga por la API
    estado = await client.get(
        f"/api/v1/insurancepolicies-service/polizas/{poliza.poliza_id}/certificado", headers=HEADERS
    )
    assert estado.json()["disponible"] is True
    assert estado.json()["ultima_generacion"]["estado"] == "GENERADO"
    descarga = await client.get(
        f"/api/v1/insurancepolicies-service/polizas/{poliza.poliza_id}/certificado/descarga", headers=HEADERS
    )
    assert descarga.status_code == 200 and descarga.headers["content-type"] == "application/pdf"
    assert descarga.content.startswith(b"%PDF-")
    if isinstance(entorno.generador, GeneradorCertificadoWeasyPrint):
        assert paginas_pdf(descarga.content) == 1
        texto = texto_pdf(descarga.content)
        for esperado in (
            poliza.numero,
            str(poliza.poliza_id),
            "María Fernanda Rodríguez Castañeda",
            "Seguro de Vida Deudores Hipotecarios",
            "13 de noviembre de 2026",
            "13 de noviembre de 2036",
            "Fallecimiento del asegurado",
            "COP 200.000.000,00",
            "IVA (19,00 %)",
            "COP 1.416.100,00",
        ):
            assert esperado in texto, esperado
    else:
        (datos, imagen, tipo) = entorno.generador.llamadas[0]
        assert imagen == FIRMA_PNG and tipo == "image/png"


async def test_un_pago_aprobado_duplicado_no_emite_otra_poliza(entorno):
    await entorno.capturar_firma()
    mensaje = entorno.enviar_pago_aprobado()
    entorno.enviar_pago_aprobado(mensaje)  # SQS entrega "al menos una vez"

    assert await entorno.consumidor_pagos.procesar_lote() == 2

    assert len(await entorno.polizas()) == 1
    assert len(await entorno.eventos()) == 1


async def test_sin_firma_la_poliza_no_se_emite_y_el_mensaje_queda_para_reintento(entorno):
    entorno.enviar_pago_aprobado()

    assert await entorno.consumidor_pagos.procesar_lote() == 0

    assert await entorno.polizas() == [] and await entorno.eventos() == []
    assert entorno.mensajes(entorno.url_pago) == 1


async def test_se_emite_cuando_la_firma_llega_antes_del_reintento(entorno):
    entorno.enviar_pago_aprobado()
    assert await entorno.consumidor_pagos.procesar_lote() == 0
    await entorno.capturar_firma()
    await asyncio.sleep(1.2)  # vence el tiempo de visibilidad y SQS reentrega

    assert await entorno.consumidor_pagos.procesar_lote() == 1

    assert len(await entorno.polizas()) == 1


async def test_un_mensaje_de_otro_tipo_o_invalido_no_emite_ni_se_borra(entorno):
    await entorno.capturar_firma()
    entorno.enviar_pago_aprobado({**mensaje_pago_aprobado(), "tipo": "PagoRechazado"})
    entorno.enviar_pago_aprobado(mensaje_pago_aprobado(monto="-1"))

    assert await entorno.consumidor_pagos.procesar_lote() == 0

    assert await entorno.polizas() == [] and entorno.mensajes(entorno.url_pago) == 2


async def test_un_fallo_al_generar_deja_auditoria_fallida_y_el_reintento_lo_completa(entorno_falso):
    entorno, generador = entorno_falso, entorno_falso.generador
    await entorno.capturar_firma()
    entorno.enviar_pago_aprobado()
    await entorno.consumidor_pagos.procesar_lote()
    await entorno.relay.publicar_pendientes()
    generador.error = GeneracionPdfError("fallo transitorio")

    assert await entorno.consumidor_certificados.procesar_lote() == 0

    (poliza,) = await entorno.polizas()
    assert poliza.estado_certificado == EstadoCertificado.PENDIENTE.value
    (fallida,) = await entorno.generaciones()
    assert fallida.estado == EstadoGeneracion.FALLIDO.value and fallida.error_codigo == "PDF_INVALIDO"
    assert entorno.mensajes(entorno.url_poliza) == 1

    generador.error = None
    await asyncio.sleep(1.2)
    assert await entorno.consumidor_certificados.procesar_lote() == 1

    estados = [g.estado for g in await entorno.generaciones()]
    assert estados == [EstadoGeneracion.FALLIDO.value, EstadoGeneracion.GENERADO.value]
    (poliza,) = await entorno.polizas()
    assert poliza.estado_certificado == EstadoCertificado.GENERADO.value


async def test_un_poliza_emitida_duplicado_no_regenera_el_certificado(entorno_falso):
    entorno, generador = entorno_falso, entorno_falso.generador
    await entorno.capturar_firma()
    entorno.enviar_pago_aprobado()
    await entorno.consumidor_pagos.procesar_lote()
    await entorno.relay.publicar_pendientes()
    mensaje = entorno.sqs.receive_message(QueueUrl=entorno.url_poliza, VisibilityTimeout=0)["Messages"][0]
    entorno.sqs.send_message(QueueUrl=entorno.url_poliza, MessageBody=mensaje["Body"])  # duplicado

    await entorno.consumidor_certificados.procesar_lote()

    assert len(generador.llamadas) == 1
    assert len(await entorno.generaciones()) == 1
