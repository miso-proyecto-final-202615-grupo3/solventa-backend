"""Pruebas de evidencias contra infraestructura real (plan de HU4.1.2 §8). Se saltan sin las variables:

- `TEST_POSTGRES_URL`: Postgres de compose (límite concurrente de evidencias).
- `TEST_S3_ENDPOINT_URL` + `TEST_S3_BUCKET` + `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`: MinIO de compose.
Dentro de la red de compose: `postgresql+asyncpg://postgres:postgres@db:5432/identity_db` y `http://minio:9000`.
"""
import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.application.use_cases.evidencias_use_cases import (
    ConfirmarCargaEvidenciaUseCase,
    SolicitarCargaEvidenciaUseCase,
    SolicitudCargaCmd,
)
from src.core.database import Base
from src.domain.siniestros.entities import Siniestro
from src.domain.siniestros.errores import LimiteEvidencias
from src.domain.siniestros.evidencias import OrigenEvidencia, TipoEvidencia
from src.domain.siniestros.politica_evidencias import PoliticaEvidencias
from src.infrastructure.persistence.catalogo_tipos_siniestro_impl import (
    SqlAlchemyCatalogoTiposSiniestro,
    invalidar_cache,
)
from src.infrastructure.persistence.models import EvidenciaSiniestroModel, SiniestroModel
from src.infrastructure.persistence.seed_tipos_siniestro import sembrar_tipos_siniestro
from src.infrastructure.persistence.siniestros_repository_impl import (
    SqlAlchemyEvidenciaRepository,
    SqlAlchemySiniestroRepository,
)
from src.infrastructure.storage.memoria import AlmacenEvidenciasEnMemoria
from src.infrastructure.storage.s3_almacen import S3AlmacenEvidencias
from tests.fakes import CLIENTE

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")
S3_URL = os.getenv("TEST_S3_ENDPOINT_URL")
S3_BUCKET = os.getenv("TEST_S3_BUCKET", "solventa-local-storage")
AHORA = datetime.now(UTC)
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 1020


def _cmd(siniestro_id: uuid.UUID, tamano: int = len(JPEG)) -> SolicitudCargaCmd:
    return SolicitudCargaCmd(
        siniestro_id=siniestro_id, cliente_id=CLIENTE, tipo=TipoEvidencia.FOTO, content_type="image/jpeg",
        tamano_bytes=tamano, origen=OrigenEvidencia.GALERIA, capturada_en=AHORA,
    )


def _siniestro() -> Siniestro:
    return Siniestro(
        poliza_id=uuid.uuid4(), tipo="EQUIPAJE", estado="REPORTADO", clave_idempotencia=str(uuid.uuid4()),
        ocurrido_en=AHORA, reportado_en=AHORA, cliente_id=CLIENTE, numero=f"SIN-T-{uuid.uuid4().hex[:8]}",
        canal="MOVIL", producto_codigo="SEGURO_VIAJE",
    )


@pytest.mark.postgres
@pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL no está definida")
async def test_solicitudes_simultaneas_no_superan_el_maximo_de_fotos():
    engine = create_async_engine(POSTGRES_URL)
    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS insuranceclaims"))
        await conn.run_sync(Base.metadata.create_all)
    siniestro = _siniestro()
    async with fabrica() as session:
        await sembrar_tipos_siniestro(session)
        await SqlAlchemySiniestroRepository(session).guardar(siniestro)
        await session.commit()
    invalidar_cache()
    almacen = AlmacenEvidenciasEnMemoria()

    async def solicitar():
        async with fabrica() as session:
            use_case = SolicitarCargaEvidenciaUseCase(
                session, SqlAlchemySiniestroRepository(session), SqlAlchemyEvidenciaRepository(session),
                SqlAlchemyCatalogoTiposSiniestro(session), almacen, PoliticaEvidencias(), lambda: AHORA, "siniestros/",
            )
            try:
                return await use_case.ejecutar(_cmd(siniestro.siniestro_id), "corr-limite")
            except LimiteEvidencias:
                return None

    try:
        resultados = await asyncio.gather(*(solicitar() for _ in range(8)))
        assert sum(r is not None for r in resultados) == 5  # fotos_max de EQUIPAJE
    finally:
        async with fabrica() as session:
            await session.execute(delete(EvidenciaSiniestroModel).where(EvidenciaSiniestroModel.siniestro_id == siniestro.siniestro_id))
            await session.execute(delete(SiniestroModel).where(SiniestroModel.siniestro_id == siniestro.siniestro_id))
            await session.commit()
        await engine.dispose()
        invalidar_cache()


@pytest.fixture
def minio():
    if not S3_URL:
        pytest.skip("TEST_S3_ENDPOINT_URL no está definida")
    return S3AlmacenEvidencias.desde_configuracion(
        bucket=S3_BUCKET, region="us-east-1", sse="AES256", kms_key_id=None, endpoint_url=S3_URL, public_endpoint_url=None
    )


async def _subir(carga, contenido: bytes, content_type: str = "image/jpeg") -> httpx.Response:
    campos = dict(carga.campos)
    campos["Content-Type"] = content_type
    async with httpx.AsyncClient(timeout=20) as client:
        # S3 exige el archivo al final del formulario; httpx envía `files` después de `data`.
        return await client.post(carga.url, data=campos, files={"file": ("evidencia", contenido, content_type)})


@pytest.mark.minio
async def test_minio_acepta_la_subida_firmada_y_se_verifica(minio):
    clave = f"siniestros/pruebas/{uuid.uuid4()}.jpg"
    carga = await minio.generar_carga(clave, "image/jpeg", 5 * 1024 * 1024, timedelta(minutes=5))

    respuesta = await _subir(carga, JPEG)
    metadatos = await minio.metadatos(clave)
    inicio = await minio.leer_inicio(clave, 12)
    await minio.eliminar(clave)

    assert respuesta.status_code in (200, 204), respuesta.text
    assert metadatos.tamano == len(JPEG) and metadatos.content_type == "image/jpeg"
    assert metadatos.cifrado == "AES256"
    assert PoliticaEvidencias.firma_valida(TipoEvidencia.FOTO, inicio)
    assert await minio.metadatos(clave) is None


@pytest.mark.minio
async def test_minio_rechaza_archivo_mas_grande_que_la_politica(minio):
    clave = f"siniestros/pruebas/{uuid.uuid4()}.jpg"
    carga = await minio.generar_carga(clave, "image/jpeg", 1024, timedelta(minutes=5))

    respuesta = await _subir(carga, JPEG + b"\x00" * 2048)

    assert respuesta.status_code in (400, 403)
    assert await minio.metadatos(clave) is None


@pytest.mark.minio
async def test_minio_rechaza_otro_content_type(minio):
    clave = f"siniestros/pruebas/{uuid.uuid4()}.jpg"
    carga = await minio.generar_carga(clave, "image/jpeg", 5 * 1024 * 1024, timedelta(minutes=5))

    respuesta = await _subir(carga, JPEG, content_type="image/png")

    assert respuesta.status_code in (400, 403)
    assert await minio.metadatos(clave) is None


@pytest.mark.minio
async def test_minio_flujo_de_confirmacion_completo(minio):
    if not POSTGRES_URL:
        pytest.skip("TEST_POSTGRES_URL no está definida")
    engine = create_async_engine(POSTGRES_URL)
    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS insuranceclaims"))
        await conn.run_sync(Base.metadata.create_all)
    siniestro = _siniestro()
    async with fabrica() as session:
        await sembrar_tipos_siniestro(session)
        await SqlAlchemySiniestroRepository(session).guardar(siniestro)
        await session.commit()
    invalidar_cache()
    try:
        async with fabrica() as session:
            args = (SqlAlchemySiniestroRepository(session), SqlAlchemyEvidenciaRepository(session))
            solicitar = SolicitarCargaEvidenciaUseCase(
                session, *args, SqlAlchemyCatalogoTiposSiniestro(session), minio, PoliticaEvidencias(),
                lambda: datetime.now(UTC), "siniestros/pruebas/",
            )
            confirmar = ConfirmarCargaEvidenciaUseCase(session, *args, minio, PoliticaEvidencias(), lambda: datetime.now(UTC))
            resultado = await solicitar.ejecutar(_cmd(siniestro.siniestro_id), "corr-minio")
            assert (await _subir(resultado.carga, JPEG)).status_code in (200, 204)
            evidencia = await confirmar.ejecutar(siniestro.siniestro_id, resultado.evidencia.evidencia_id, CLIENTE, "corr-minio")
            assert evidencia.estado == "CARGADA" and evidencia.tamano_bytes == len(JPEG)
            await minio.eliminar(evidencia.objeto_clave)
    finally:
        async with fabrica() as session:
            await session.execute(delete(EvidenciaSiniestroModel).where(EvidenciaSiniestroModel.siniestro_id == siniestro.siniestro_id))
            await session.execute(delete(SiniestroModel).where(SiniestroModel.siniestro_id == siniestro.siniestro_id))
            await session.commit()
        await engine.dispose()
        invalidar_cache()
