import uuid
from datetime import date
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.ports.kyc_aml import KycAmlProvider, ProveedorKycAmlError
from src.core.config import settings
from src.core.database import Base
from src.domain.clientes.value_objects import EstadoKYC
from src.domain.verificaciones_kyc_aml.entities import (
    InicioProveedor,
    ResultadoChequeo,
    ResultadoProveedor,
    RutasDocumentos,
    construir_ruta,
)
from src.domain.verificaciones_kyc_aml.repositories import (
    AlmacenamientoDocumentosError,
    DocumentoVerificacionRepository,
)
from src.infrastructure.persistence.models import ClienteModel, VerificacionKycAmlModel
from src.infrastructure.storage.documento_verificacion_local_repository import (
    LocalDocumentoVerificacionRepository,
)
from src.main import app
from src.presentation.dependencies import (
    get_db,
    get_documento_verificacion_repository,
    get_kyc_aml_provider,
)

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
URL = "/api/v1/identity-service/clientes/{}/verificaciones-kyc-aml"


class FakeDocumentos(DocumentoVerificacionRepository):
    def __init__(self):
        self.guardados = []
        self.fallar = False

    async def guardar(self, cliente_id, verificacion_id, frontal, reverso):
        if self.fallar:
            raise AlmacenamientoDocumentosError("s3 caído")
        self.guardados.append((cliente_id, verificacion_id))
        return RutasDocumentos(
            frontal="s3://bucket/" + construir_ruta(cliente_id, verificacion_id, "documento-frontal.jpg"),
            reverso="s3://bucket/" + construir_ruta(cliente_id, verificacion_id, "documento-reverso.jpg"),
        )


class FakeProveedor(KycAmlProvider):
    nombre = "mock_kyc"

    def __init__(self):
        self.iniciadas = []
        self.fallar_inicio = False
        self.fallar_consulta = False
        self.kyc = ResultadoChequeo.APROBADO
        self.aml = ResultadoChequeo.APROBADO

    async def iniciar_verificacion(self, cliente_id, verificacion_id, rutas, frontal, reverso, correlation_id):
        if self.fallar_inicio:
            raise ProveedorKycAmlError("PROVEEDOR_NO_DISPONIBLE", "timeout")
        externo = str(uuid.uuid4())
        self.iniciadas.append((verificacion_id, externo, rutas, correlation_id))
        return InicioProveedor(externo, {"verification_id": externo})

    async def consultar_resultado(self, verificacion_externa_id, correlation_id):
        if self.fallar_consulta:
            raise ProveedorKycAmlError("PROVEEDOR_HTTP_500", "error")
        return ResultadoProveedor(self.kyc, self.aml, {"kyc_status": self.kyc.value})


@pytest.fixture
def documentos():
    return FakeDocumentos()


@pytest.fixture
def proveedor():
    return FakeProveedor()


@pytest.fixture
async def api(documentos, proveedor):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    async def override_proveedor():
        yield proveedor

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_documento_verificacion_repository] = lambda: documentos
    app.dependency_overrides[get_kyc_aml_provider] = override_proveedor
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, factory
    app.dependency_overrides.clear()
    await engine.dispose()


async def _cliente(factory, correo="ana.perez@example.com", documento="1020304050") -> uuid.UUID:
    async with factory() as session:
        modelo = ClienteModel(
            nombres="Ana", apellidos="Pérez", tipo_documento="CC",
            numero_identificacion=documento, correo=correo,
            fecha_nacimiento=date(1990, 5, 15), pais_residencia="Colombia",
            telefono="+573001234567", estado_kyc=EstadoKYC.PENDIENTE,
        )
        session.add(modelo)
        await session.commit()
        return modelo.id


def _archivos(frontal=JPEG, reverso=PNG, tipo_frontal="image/jpeg", tipo_reverso="image/png"):
    return {
        "documento_frontal": ("frontal", frontal, tipo_frontal),
        "documento_reverso": ("reverso", reverso, tipo_reverso),
    }


async def _estado_cliente(factory, cliente_id):
    async with factory() as session:
        return (await session.get(ClienteModel, cliente_id)).estado_kyc


async def _filas(factory):
    async with factory() as session:
        return (await session.execute(select(VerificacionKycAmlModel))).scalars().all()


async def test_inicia_verificacion_y_audita_el_intento(api, documentos, proveedor):
    client, factory = api
    cliente_id = await _cliente(factory)

    response = await client.post(
        URL.format(cliente_id), files=_archivos(), headers={"X-Correlation-Id": "corr-1"}
    )

    assert response.status_code == 202
    cuerpo = response.json()
    assert cuerpo["estado"] == "INICIADA"
    assert cuerpo["fecha"]
    (fila,) = await _filas(factory)
    assert str(fila.id) == cuerpo["verificacion_id"]
    assert fila.cliente_id == cliente_id
    assert fila.estado == "INICIADA"
    assert fila.proveedor == "mock_kyc"
    assert fila.proveedor_verificacion_id == proveedor.iniciadas[0][1]
    assert fila.correlation_id == "corr-1"
    assert fila.ruta_documento_frontal.startswith(f"s3://bucket/verificaciones-kyc-aml/{cliente_id}/{fila.id}/")
    assert fila.respuesta_inicio == {"verification_id": fila.proveedor_verificacion_id}
    assert await _estado_cliente(factory, cliente_id) == EstadoKYC.PENDIENTE


async def test_inicia_con_almacenamiento_local_y_audita_rutas(
    api, proveedor, tmp_path, monkeypatch
):
    client, factory = api
    cliente_id = await _cliente(factory)
    monkeypatch.delitem(app.dependency_overrides, get_documento_verificacion_repository)
    monkeypatch.setattr(settings, "KYC_DOCUMENT_STORAGE", "local")
    monkeypatch.setattr(
        "src.presentation.dependencies.LocalDocumentoVerificacionRepository",
        lambda: LocalDocumentoVerificacionRepository(tmp_path),
    )
    iniciar = proveedor.iniciar_verificacion

    async def comprobar_documentos(
        cliente_id, verificacion_id, rutas, frontal, reverso, correlation_id
    ):
        assert Path(rutas.frontal).read_bytes() == frontal.contenido
        assert Path(rutas.reverso).read_bytes() == reverso.contenido
        return await iniciar(cliente_id, verificacion_id, rutas, frontal, reverso, correlation_id)

    proveedor.iniciar_verificacion = comprobar_documentos
    get_documento_verificacion_repository.cache_clear()
    try:
        response = await client.post(URL.format(cliente_id), files=_archivos())
    finally:
        get_documento_verificacion_repository.cache_clear()

    assert response.status_code == 202
    (fila,) = await _filas(factory)
    base = tmp_path / "verificaciones-kyc-aml" / str(cliente_id) / str(fila.id)
    assert fila.ruta_documento_frontal == str(base / "documento-frontal.jpg")
    assert fila.ruta_documento_reverso == str(base / "documento-reverso.png")
    assert proveedor.iniciadas[0][2].frontal == fila.ruta_documento_frontal


async def test_fallo_de_almacenamiento_local_es_auditado(api, proveedor, tmp_path):
    client, factory = api
    cliente_id = await _cliente(factory)
    app.dependency_overrides[get_documento_verificacion_repository] = (
        lambda: LocalDocumentoVerificacionRepository(tmp_path / "inexistente")
    )

    response = await client.post(URL.format(cliente_id), files=_archivos())

    assert response.status_code == 503
    (fila,) = await _filas(factory)
    assert fila.estado == "ERROR"
    assert fila.error_codigo == "ALMACENAMIENTO_NO_DISPONIBLE"
    assert proveedor.iniciadas == []


async def test_cliente_inexistente_devuelve_404(api):
    client, _ = api

    response = await client.post(URL.format(uuid.uuid4()), files=_archivos())

    assert response.status_code == 404


async def test_exige_los_dos_documentos(api):
    client, factory = api
    cliente_id = await _cliente(factory)

    response = await client.post(
        URL.format(cliente_id), files={"documento_frontal": ("f", JPEG, "image/jpeg")}
    )

    assert response.status_code == 422
    assert response.json()["detail"]["codigo"] == "DOCUMENTOS_INCOMPLETOS"


@pytest.mark.parametrize(
    ("frontal", "tipo", "codigo", "http"),
    [
        (JPEG, "application/pdf", "FORMATO_NO_SOPORTADO", 415),
        (b"no-es-una-imagen", "image/jpeg", "FORMATO_NO_SOPORTADO", 415),
        (b"", "image/jpeg", "DOCUMENTO_VACIO", 422),
        (JPEG + b"0" * (5 * 1024 * 1024), "image/jpeg", "DOCUMENTO_DEMASIADO_GRANDE", 413),
    ],
)
async def test_valida_tipo_y_tamano(api, documentos, frontal, tipo, codigo, http):
    client, factory = api
    cliente_id = await _cliente(factory)

    response = await client.post(
        URL.format(cliente_id), files=_archivos(frontal=frontal, tipo_frontal=tipo)
    )

    assert response.status_code == http
    assert response.json()["detail"]["codigo"] == codigo
    assert documentos.guardados == []
    assert await _filas(factory) == []


async def test_idempotencia_reutiliza_el_intento_con_la_misma_clave(api, proveedor):
    client, factory = api
    cliente_id = await _cliente(factory)
    headers = {"Idempotency-Key": "reintento-1"}

    primero = await client.post(URL.format(cliente_id), files=_archivos(), headers=headers)
    segundo = await client.post(URL.format(cliente_id), files=_archivos(), headers=headers)

    assert segundo.status_code == 202
    assert segundo.json()["verificacion_id"] == primero.json()["verificacion_id"]
    assert segundo.json()["estado"] == "INICIADA"
    assert len(await _filas(factory)) == 1
    assert len(proveedor.iniciadas) == 1


async def test_idempotencia_rechaza_clave_con_otros_documentos(api):
    client, factory = api
    cliente_id = await _cliente(factory)
    headers = {"Idempotency-Key": "k1"}
    await client.post(URL.format(cliente_id), files=_archivos(), headers=headers)

    response = await client.post(
        URL.format(cliente_id), files=_archivos(frontal=JPEG + b"1"), headers=headers
    )

    assert response.status_code == 409
    assert response.json()["detail"]["codigo"] == "IDEMPOTENCY_KEY_REUTILIZADA"


async def test_sin_clave_cada_llamada_es_un_intento_nuevo(api):
    client, factory = api
    cliente_id = await _cliente(factory)

    await client.post(URL.format(cliente_id), files=_archivos())
    await client.post(URL.format(cliente_id), files=_archivos())

    assert len(await _filas(factory)) == 2


async def test_falla_de_s3_registra_error_y_el_reintento_con_la_misma_clave_lo_completa(
    api, documentos, proveedor
):
    client, factory = api
    cliente_id = await _cliente(factory)
    headers = {"Idempotency-Key": "k-s3", "X-Correlation-Id": "corr-err"}
    documentos.fallar = True

    fallido = await client.post(URL.format(cliente_id), files=_archivos(), headers=headers)

    assert fallido.status_code == 503
    (fila,) = await _filas(factory)
    assert fila.estado == "ERROR"
    assert fila.error_codigo == "ALMACENAMIENTO_NO_DISPONIBLE"
    assert "corr-err" in fila.error_detalle
    assert proveedor.iniciadas == []

    documentos.fallar = False
    reintento = await client.post(URL.format(cliente_id), files=_archivos(), headers=headers)

    assert reintento.status_code == 202
    assert reintento.json()["verificacion_id"] == str(fila.id)
    (fila,) = await _filas(factory)
    assert fila.estado == "INICIADA"
    assert fila.error_codigo is None


async def test_falla_del_proveedor_queda_auditada(api):
    client, factory = api
    cliente_id = await _cliente(factory)
    api_proveedor = app.dependency_overrides[get_kyc_aml_provider]

    async for proveedor in api_proveedor():
        proveedor.fallar_inicio = True
    response = await client.post(URL.format(cliente_id), files=_archivos())

    assert response.status_code == 503
    (fila,) = await _filas(factory)
    assert fila.estado == "ERROR"
    assert fila.error_codigo == "PROVEEDOR_NO_DISPONIBLE"


async def _iniciar(client, cliente_id, **kwargs) -> str:
    response = await client.post(URL.format(cliente_id), files=_archivos(), **kwargs)
    assert response.status_code == 202
    return response.json()["verificacion_id"]


@pytest.mark.parametrize(
    ("kyc", "aml", "estado", "estado_cliente"),
    [
        (ResultadoChequeo.APROBADO, ResultadoChequeo.APROBADO, "APROBADO", EstadoKYC.VALIDADO),
        (ResultadoChequeo.APROBADO, ResultadoChequeo.RECHAZADO, "RECHAZADO", EstadoKYC.RECHAZADO),
        (ResultadoChequeo.RECHAZADO, ResultadoChequeo.APROBADO, "RECHAZADO", EstadoKYC.RECHAZADO),
        (ResultadoChequeo.PENDIENTE, ResultadoChequeo.APROBADO, "PENDIENTE", EstadoKYC.PENDIENTE),
    ],
)
async def test_consulta_resultado_y_actualiza_estado_kyc(
    api, proveedor, kyc, aml, estado, estado_cliente
):
    client, factory = api
    cliente_id = await _cliente(factory)
    verificacion_id = await _iniciar(client, cliente_id)
    proveedor.kyc, proveedor.aml = kyc, aml

    response = await client.get(f"{URL.format(cliente_id)}/{verificacion_id}")

    assert response.status_code == 200
    assert response.json()["verificacion_id"] == verificacion_id
    assert response.json()["cliente_id"] == str(cliente_id)
    assert response.json()["resultado_kyc"] == kyc.value
    assert response.json()["resultado_aml"] == aml.value
    assert response.json()["estado"] == estado
    assert await _estado_cliente(factory, cliente_id) == estado_cliente
    (fila,) = await _filas(factory)
    assert fila.respuesta_resultado is not None
    assert (fila.resultado_en is not None) == (estado != "PENDIENTE")


async def test_resultado_final_no_se_recalcula(api, proveedor):
    client, factory = api
    cliente_id = await _cliente(factory)
    verificacion_id = await _iniciar(client, cliente_id)
    await client.get(f"{URL.format(cliente_id)}/{verificacion_id}")
    proveedor.kyc = ResultadoChequeo.RECHAZADO

    response = await client.get(f"{URL.format(cliente_id)}/{verificacion_id}")

    assert response.json()["estado"] == "APROBADO"


async def test_resultado_de_intento_anterior_no_pisa_al_mas_reciente(api, proveedor):
    client, factory = api
    cliente_id = await _cliente(factory)
    anterior = await _iniciar(client, cliente_id)
    reciente = await _iniciar(client, cliente_id)
    proveedor.kyc = ResultadoChequeo.RECHAZADO
    await client.get(f"{URL.format(cliente_id)}/{reciente}")
    proveedor.kyc = ResultadoChequeo.APROBADO

    response = await client.get(f"{URL.format(cliente_id)}/{anterior}")

    assert response.json()["estado"] == "APROBADO"
    assert await _estado_cliente(factory, cliente_id) == EstadoKYC.RECHAZADO


async def test_error_del_proveedor_al_consultar_conserva_el_estado(api, proveedor):
    client, factory = api
    cliente_id = await _cliente(factory)
    verificacion_id = await _iniciar(client, cliente_id)
    proveedor.fallar_consulta = True

    response = await client.get(
        f"{URL.format(cliente_id)}/{verificacion_id}", headers={"X-Correlation-Id": "corr-get"}
    )

    assert response.status_code == 503
    (fila,) = await _filas(factory)
    assert fila.estado == "INICIADA"
    assert fila.error_codigo == "PROVEEDOR_HTTP_500"
    assert "corr-get" in fila.error_detalle
    assert await _estado_cliente(factory, cliente_id) == EstadoKYC.PENDIENTE


async def test_consulta_de_verificacion_inexistente_o_de_otro_cliente(api):
    client, factory = api
    cliente_id = await _cliente(factory)
    otro = await _cliente(factory, correo="otro@example.com", documento="999")
    verificacion_id = await _iniciar(client, cliente_id)

    ajena = await client.get(f"{URL.format(otro)}/{verificacion_id}")
    inexistente = await client.get(f"{URL.format(cliente_id)}/{uuid.uuid4()}")

    assert ajena.status_code == 404
    assert inexistente.status_code == 404


async def test_escritura_concurrente_no_sobrescribe_resultado_mas_reciente(api, proveedor):
    client, factory = api
    cliente_id = await _cliente(factory)
    verificacion_id = await _iniciar(client, cliente_id)

    from src.infrastructure.persistence.verificacion_kyc_aml_repository_impl import (
        SqlAlchemyVerificacionKycAmlRepository,
    )

    async with factory() as s1, factory() as s2:
        r1, r2 = SqlAlchemyVerificacionKycAmlRepository(s1), SqlAlchemyVerificacionKycAmlRepository(s2)
        v1 = await r1.obtener(cliente_id, uuid.UUID(verificacion_id))
        v2 = await r2.obtener(cliente_id, uuid.UUID(verificacion_id))
        v2.error_codigo = "NUEVO"
        assert await r2.actualizar(v2)
        await s2.commit()
        v1.error_codigo = "VIEJO"
        assert not await r1.actualizar(v1)
        await s1.rollback()

    (fila,) = await _filas(factory)
    assert fila.error_codigo == "NUEVO"
