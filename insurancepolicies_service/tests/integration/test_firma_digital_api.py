import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.firmas.entities import FirmaDigital, calcular_fingerprint
from src.domain.firmas.repositories import AlmacenamientoFirmaError, FirmaDuplicadaError
from src.infrastructure.persistence.firma_digital_repository_impl import (
    SqlAlchemyFirmaDigitalRepository,
)
from src.infrastructure.persistence.models import FirmaDigitalModel
from src.infrastructure.storage.firma_local_repository import (
    LocalAlmacenamientoFirmaRepository,
)
from src.main import app
from src.presentation.dependencies import (
    get_almacenamiento_firma_repository,
    get_db,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"firma-manuscrita"
URL = "/api/v1/insurancepolicies-service/cotizaciones/{}/firma-digital"


class AlmacenamientoQueFalla(LocalAlmacenamientoFirmaRepository):
    async def guardar(self, ruta, archivo):
        raise AlmacenamientoFirmaError("S3 caído")


@pytest.fixture
def storage(tmp_path) -> LocalAlmacenamientoFirmaRepository:
    return LocalAlmacenamientoFirmaRepository(tmp_path)


@pytest.fixture
async def client(
    db_session: AsyncSession, storage
) -> AsyncGenerator[AsyncClient, None]:
    async def _db():
        yield db_session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_almacenamiento_firma_repository] = lambda: storage
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


def _datos(cliente_id=None, producto_id=None) -> dict:
    return {
        "cliente_id": str(cliente_id or uuid.uuid4()),
        "producto_id": str(producto_id or uuid.uuid4()),
    }


async def _firmar(
    client: AsyncClient,
    cotizacion_id: uuid.UUID,
    datos: dict,
    contenido: bytes = PNG,
    clave: str | None = "clave-1",
    content_type: str = "image/png",
):
    headers = {"Idempotency-Key": clave} if clave else {}
    return await client.post(
        URL.format(cotizacion_id),
        data=datos,
        files=[("firma", ("firma.png", contenido, content_type))],
        headers=headers,
    )


async def test_captura_firma_guarda_archivo_y_auditoria(
    client: AsyncClient, db_session: AsyncSession, tmp_path
):
    cotizacion_id = uuid.uuid4()
    datos = _datos()

    response = await _firmar(client, cotizacion_id, datos)

    assert response.status_code == 201
    cuerpo = response.json()
    assert cuerpo["estado"] == "CAPTURADA"
    assert cuerpo["cotizacion_id"] == str(cotizacion_id)
    assert cuerpo["cliente_id"] == datos["cliente_id"]
    assert cuerpo["producto_id"] == datos["producto_id"]
    assert cuerpo["proveedor_firma"] == "CANVAS_MANUSCRITA"
    assert "ruta_imagen" not in cuerpo

    fila = (await db_session.execute(select(FirmaDigitalModel))).scalar_one()
    assert fila.ruta_imagen == (
        f"firma-digital/{datos['cliente_id']}/{cuerpo['firma_id']}/firma.png"
    )
    assert (tmp_path / fila.ruta_imagen).read_bytes() == PNG
    assert fila.tamano_bytes == len(PNG)
    assert fila.firma_hash == cuerpo["firma_hash"]
    assert fila.fingerprint_contrato == calcular_fingerprint(
        fila.firma_hash,
        fila.capturada_en.replace(tzinfo=UTC),
        fila.cliente_id,
        fila.cotizacion_id,
        fila.producto_id,
        fila.proveedor_firma,
    )
    assert not {c.name for c in FirmaDigitalModel.__table__.columns} & {
        "ip_cliente",
        "user_agent",
        "browser_agent",
    }


async def test_reintento_con_la_misma_clave_devuelve_la_misma_firma(
    client: AsyncClient, db_session: AsyncSession
):
    cotizacion_id = uuid.uuid4()
    datos = _datos()

    primera = await _firmar(client, cotizacion_id, datos)
    segunda = await _firmar(client, cotizacion_id, datos)

    assert segunda.status_code == 200
    assert segunda.json() == primera.json()
    filas = (await db_session.execute(select(FirmaDigitalModel))).scalars().all()
    assert len(filas) == 1


async def test_clave_reutilizada_con_otra_firma_es_conflicto(client: AsyncClient):
    cotizacion_id = uuid.uuid4()
    datos = _datos()
    await _firmar(client, cotizacion_id, datos)

    response = await _firmar(client, cotizacion_id, datos, contenido=PNG + b"otra")

    assert response.status_code == 409
    assert response.json()["detail"]["codigo"] == "IDEMPOTENCY_KEY_REUTILIZADA"


async def test_nueva_firma_reemplaza_a_la_anterior(
    client: AsyncClient, db_session: AsyncSession
):
    cotizacion_id = uuid.uuid4()
    datos = _datos()
    await _firmar(client, cotizacion_id, datos, clave="k1")

    response = await _firmar(client, cotizacion_id, datos, contenido=PNG + b"2", clave="k2")

    assert response.status_code == 201
    estados = sorted(
        f.estado for f in (await db_session.execute(select(FirmaDigitalModel))).scalars()
    )
    assert estados == ["CAPTURADA", "REEMPLAZADA"]
    vigente = await client.get(URL.format(cotizacion_id))
    assert vigente.status_code == 200
    assert vigente.json()["firma_id"] == response.json()["firma_id"]


async def test_consulta_sin_firma_retorna_404(client: AsyncClient):
    response = await client.get(URL.format(uuid.uuid4()))

    assert response.status_code == 404
    assert response.json()["detail"]["codigo"] == "FIRMA_NO_ENCONTRADA"


async def test_requiere_clave_de_idempotencia_valida(client: AsyncClient):
    for clave in (None, "con espacios"):
        response = await _firmar(client, uuid.uuid4(), _datos(), clave=clave)

        assert response.status_code == 422
        assert response.json()["detail"]["codigo"] == "IDEMPOTENCY_KEY_INVALIDA"


@pytest.mark.parametrize(
    ("contenido", "content_type", "status_esperado", "codigo"),
    [
        (PNG, "image/gif", 415, "FORMATO_NO_SOPORTADO"),
        (b"no es png", "image/png", 415, "FORMATO_NO_SOPORTADO"),
        (b"", "image/png", 422, "FIRMA_VACIA"),
        (PNG + b"x" * (1024 * 1024), "image/png", 413, "FIRMA_DEMASIADO_GRANDE"),
    ],
)
async def test_rechaza_archivos_invalidos(
    client: AsyncClient, db_session: AsyncSession, contenido, content_type, status_esperado, codigo
):
    response = await _firmar(
        client, uuid.uuid4(), _datos(), contenido=contenido, content_type=content_type
    )

    assert response.status_code == status_esperado
    assert response.json()["detail"]["codigo"] == codigo
    assert (await db_session.execute(select(FirmaDigitalModel))).first() is None


async def test_rechaza_cantidad_de_archivos_distinta_de_uno(client: AsyncClient):
    cotizacion_id = uuid.uuid4()
    headers = {"Idempotency-Key": "k"}

    sin_archivo = await client.post(URL.format(cotizacion_id), data=_datos(), headers=headers)
    dos_archivos = await client.post(
        URL.format(cotizacion_id),
        data=_datos(),
        files=[
            ("firma", ("a.png", PNG, "image/png")),
            ("firma", ("b.png", PNG, "image/png")),
        ],
        headers=headers,
    )

    for response in (sin_archivo, dos_archivos):
        assert response.status_code == 422
        assert response.json()["detail"]["codigo"] == "FIRMA_CANTIDAD_INVALIDA"


async def test_fallo_de_almacenamiento_no_deja_fila_y_conserva_la_firma_previa(
    client: AsyncClient, db_session: AsyncSession, storage
):
    cotizacion_id = uuid.uuid4()
    datos = _datos()
    await _firmar(client, cotizacion_id, datos, clave="k1")
    app.dependency_overrides[get_almacenamiento_firma_repository] = lambda: (
        AlmacenamientoQueFalla(storage.directorio_base)
    )

    response = await _firmar(client, cotizacion_id, datos, contenido=PNG + b"2", clave="k2")

    assert response.status_code == 503
    assert response.json()["detail"]["codigo"] == "ALMACENAMIENTO_NO_DISPONIBLE"
    filas = (await db_session.execute(select(FirmaDigitalModel))).scalars().all()
    assert [(f.idempotency_key, f.estado) for f in filas] == [("k1", "CAPTURADA")]


async def test_indice_unico_impide_dos_firmas_vigentes_por_cotizacion(
    db_session: AsyncSession,
):
    repo = SqlAlchemyFirmaDigitalRepository(db_session)
    cotizacion_id = uuid.uuid4()

    def _firma(clave: str) -> FirmaDigital:
        return FirmaDigital(
            cliente_id=uuid.uuid4(),
            cotizacion_id=cotizacion_id,
            producto_id=uuid.uuid4(),
            proveedor_firma="CANVAS_MANUSCRITA",
            ruta_imagen="firma-digital/x/y/firma.png",
            content_type="image/png",
            tamano_bytes=1,
            firma_hash="a" * 64,
            fingerprint_contrato="b" * 64,
            capturada_en=datetime.now(UTC),
            idempotency_key=clave,
            correlation_id="c",
        )

    await repo.crear(_firma("k1"))
    with pytest.raises(FirmaDuplicadaError):
        await repo.crear(_firma("k2"))
