import uuid
from collections.abc import AsyncGenerator
from datetime import timedelta
from decimal import Decimal

import pytest
from emision_fakes import (
    AHORA,
    CLIENTE_ID,
    COBERTURA_ID,
    COTIZACION_ID,
    contrato_de,
    poliza_emitida,
)
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.domain.certificados.entities import EstadoGeneracion, GeneracionCertificado
from src.domain.certificados.repositories import AlmacenamientoCertificadoError
from src.domain.polizas.entities import EstadoCertificado, PolizaCobertura
from src.infrastructure.persistence.generacion_certificado_repository_impl import (
    SqlAlchemyGeneracionCertificadoRepository,
)
from src.infrastructure.persistence.poliza_repository_impl import SqlAlchemyPolizaRepository
from src.infrastructure.storage.certificado_local_repository import (
    LocalAlmacenamientoCertificadoRepository,
)
from src.main import app
from src.presentation.dependencies import get_almacenamiento_certificado_repository, get_db

PDF = b"%PDF-1.7\ncontenido del certificado"
HEADERS = {"X-Client-Id": str(CLIENTE_ID)}


@pytest.fixture
def almacenamiento(tmp_path) -> LocalAlmacenamientoCertificadoRepository:
    return LocalAlmacenamientoCertificadoRepository(tmp_path)


@pytest.fixture
async def client(
    session_factory: async_sessionmaker, almacenamiento
) -> AsyncGenerator[AsyncClient, None]:
    async def _db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_almacenamiento_certificado_repository] = lambda: almacenamiento
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def sembrar(session_factory, **cambios):
    """Una póliza emitida con su contrato, como la deja la emisión."""
    poliza = poliza_emitida(**cambios)
    poliza.coberturas = [
        PolizaCobertura(
            poliza_id=poliza.poliza_id,
            cobertura_id=COBERTURA_ID,
            limite_asegurado=Decimal("200000000.00"),
            deducible=Decimal("0.00"),
            prima=Decimal("1416100.00"),
        )
    ]
    async with session_factory() as session:
        polizas = SqlAlchemyPolizaRepository(session)
        await polizas.guardar(poliza)
        await polizas.guardar_contrato(contrato_de(poliza))
        await session.commit()
    return poliza


def url_poliza(cotizacion_id=COTIZACION_ID) -> str:
    return f"/api/v1/insurancepolicies-service/cotizaciones/{cotizacion_id}/poliza"


def url_certificado(poliza_id, sufijo="") -> str:
    return f"/api/v1/insurancepolicies-service/polizas/{poliza_id}/certificado{sufijo}"


async def test_resumen_de_la_poliza_por_cotizacion(client, session_factory):
    poliza = await sembrar(session_factory)

    response = await client.get(url_poliza(), headers=HEADERS)

    assert response.status_code == 200
    assert response.json() == {
        "poliza_id": str(poliza.poliza_id),
        "numero": "POL-20261113-AB12CD34",
        "estado": "EMITIDA",
        "cotizacion_id": str(COTIZACION_ID),
        "titular_nombre": "María Fernanda Rodríguez Castañeda",
        "vigencia_desde": "2026-11-13T13:00:00Z",
        "vigencia_hasta": "2036-11-13T13:00:00Z",
        "prima": "1416100.00",
        "moneda": "COP",
        "estado_certificado": "PENDIENTE",
    }


async def test_resumen_sin_poliza_emitida_aun(client):
    response = await client.get(url_poliza(), headers=HEADERS)

    assert response.status_code == 404
    assert response.json()["detail"]["codigo"] == "POLIZA_NO_ENCONTRADA"


async def test_resumen_de_la_poliza_de_otro_cliente_es_403(client, session_factory):
    await sembrar(session_factory)

    response = await client.get(url_poliza(), headers={"X-Client-Id": str(uuid.uuid4())})

    assert response.status_code == 403
    assert response.json()["detail"]["codigo"] == "ACCESO_DENEGADO"
    assert "Rodríguez" not in response.text


@pytest.mark.parametrize("headers", [{}, {"X-Client-Id": "no-es-uuid"}])
async def test_exige_el_cliente_en_los_tres_endpoints(client, session_factory, headers):
    poliza = await sembrar(session_factory)

    for url in (url_poliza(), url_certificado(poliza.poliza_id), url_certificado(poliza.poliza_id, "/descarga")):
        response = await client.get(url, headers=headers)
        assert response.status_code == 422, url


async def test_estado_pendiente_sin_intentos(client, session_factory):
    poliza = await sembrar(session_factory)

    response = await client.get(url_certificado(poliza.poliza_id), headers=HEADERS)

    assert response.status_code == 200
    assert response.json() == {
        "poliza_id": str(poliza.poliza_id),
        "estado_certificado": "PENDIENTE",
        "disponible": False,
        "ultima_generacion": None,
    }


async def test_estado_con_un_intento_fallido_no_expone_detalles_internos(client, session_factory):
    poliza = await sembrar(session_factory)
    async with session_factory() as session:
        await SqlAlchemyGeneracionCertificadoRepository(session).crear(
            GeneracionCertificado(
                poliza_id=poliza.poliza_id,
                cliente_id=CLIENTE_ID,
                plantilla="certificado_poliza.html",
                datos_plantilla={"titular": {"nombre": "secreto"}},
                iniciada_en=AHORA,
                finalizada_en=AHORA + timedelta(seconds=2),
                correlation_id="c",
                estado=EstadoGeneracion.FALLIDO,
                error_codigo="PDF_INVALIDO",
                error_detalle="GeneracionPdfError: /srv/app/detalle interno",
            )
        )
        await session.commit()

    response = await client.get(url_certificado(poliza.poliza_id), headers=HEADERS)

    cuerpo = response.json()
    assert cuerpo["estado_certificado"] == "PENDIENTE" and cuerpo["disponible"] is False
    assert cuerpo["ultima_generacion"] == {
        "estado": "FALLIDO",
        "plantilla": "certificado_poliza.html",
        "iniciada_en": "2026-11-13T14:00:00Z",
        "finalizada_en": "2026-11-13T14:00:02Z",
        "error_codigo": "PDF_INVALIDO",
    }
    assert "detalle interno" not in response.text and "secreto" not in response.text


async def test_estado_generado(client, session_factory):
    poliza = await sembrar(session_factory)
    async with session_factory() as session:
        await SqlAlchemyPolizaRepository(session).actualizar_certificado(
            poliza.poliza_id, EstadoCertificado.GENERADO, "ruta.pdf"
        )
        await session.commit()

    response = await client.get(url_certificado(poliza.poliza_id), headers=HEADERS)

    assert response.json()["estado_certificado"] == "GENERADO"
    assert response.json()["disponible"] is True
    assert "ruta" not in response.text


@pytest.mark.parametrize("sufijo", ["", "/descarga"])
async def test_certificado_de_poliza_inexistente_o_ajena(client, session_factory, sufijo):
    poliza = await sembrar(session_factory)

    inexistente = await client.get(url_certificado(uuid.uuid4(), sufijo), headers=HEADERS)
    ajena = await client.get(
        url_certificado(poliza.poliza_id, sufijo), headers={"X-Client-Id": str(uuid.uuid4())}
    )

    assert inexistente.status_code == 404 and inexistente.json()["detail"]["codigo"] == "POLIZA_NO_ENCONTRADA"
    assert ajena.status_code == 403 and ajena.json()["detail"]["codigo"] == "ACCESO_DENEGADO"


async def marcar_generado(session_factory, almacenamiento, poliza, contenido=PDF, escribir=True):
    ruta = f"certificados-poliza/{poliza.cliente_id}/{poliza.poliza_id}/certificado-poliza.pdf"
    if escribir:
        await almacenamiento.guardar(ruta, contenido)
    async with session_factory() as session:
        await SqlAlchemyPolizaRepository(session).actualizar_certificado(
            poliza.poliza_id, EstadoCertificado.GENERADO, ruta
        )
        await session.commit()


async def test_descarga_el_pdf_con_cabeceras_seguras(client, session_factory, almacenamiento):
    poliza = await sembrar(session_factory)
    await marcar_generado(session_factory, almacenamiento, poliza)

    response = await client.get(url_certificado(poliza.poliza_id, "/descarga"), headers=HEADERS)

    assert response.status_code == 200
    assert response.content == PDF
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'attachment; filename="certificado-POL-20261113-AB12CD34.pdf"'
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_el_nombre_del_archivo_no_permite_inyectar_cabeceras(client, session_factory, almacenamiento):
    poliza = await sembrar(session_factory, numero='POL "9"\r\nX-Inyectado: 1/../é')
    await marcar_generado(session_factory, almacenamiento, poliza)

    response = await client.get(url_certificado(poliza.poliza_id, "/descarga"), headers=HEADERS)

    disposicion = response.headers["content-disposition"]
    assert "\r" not in disposicion and "\n" not in disposicion and "x-inyectado" not in response.headers
    assert disposicion == 'attachment; filename="certificado-POL__9___X-Inyectado__1_..__.pdf"'


async def test_descarga_antes_de_generar_es_409(client, session_factory):
    poliza = await sembrar(session_factory)

    response = await client.get(url_certificado(poliza.poliza_id, "/descarga"), headers=HEADERS)

    assert response.status_code == 409
    assert response.json()["detail"]["codigo"] == "CERTIFICADO_NO_GENERADO"
    assert "PENDIENTE" in response.json()["detail"]["mensaje"]


async def test_descarga_con_el_archivo_ausente_es_404(client, session_factory, almacenamiento):
    poliza = await sembrar(session_factory)
    await marcar_generado(session_factory, almacenamiento, poliza, escribir=False)

    response = await client.get(url_certificado(poliza.poliza_id, "/descarga"), headers=HEADERS)

    assert response.status_code == 404
    assert response.json()["detail"]["codigo"] == "CERTIFICADO_NO_ENCONTRADO"


async def test_descarga_con_el_almacenamiento_caido_es_503(client, session_factory, almacenamiento):
    poliza = await sembrar(session_factory)
    await marcar_generado(session_factory, almacenamiento, poliza)

    class AlmacenamientoCaido(LocalAlmacenamientoCertificadoRepository):
        async def leer(self, ruta):
            raise AlmacenamientoCertificadoError("S3 caído")

    app.dependency_overrides[get_almacenamiento_certificado_repository] = lambda: AlmacenamientoCaido(
        almacenamiento.directorio_base
    )

    response = await client.get(url_certificado(poliza.poliza_id, "/descarga"), headers=HEADERS)

    assert response.status_code == 503
    assert response.json()["detail"]["codigo"] == "ALMACENAMIENTO_NO_DISPONIBLE"
    assert "S3 caído" not in response.text


async def test_openapi_expone_los_tres_endpoints_con_el_prefijo_del_servicio(client):
    paths = (await client.get("/openapi.json")).json()["paths"]
    prefijo = "/api/v1/insurancepolicies-service"

    assert f"{prefijo}/cotizaciones/{{cotizacion_id}}/poliza" in paths
    assert f"{prefijo}/polizas/{{poliza_id}}/certificado" in paths
    descarga = paths[f"{prefijo}/polizas/{{poliza_id}}/certificado/descarga"]["get"]
    assert "application/pdf" in descarga["responses"]["200"]["content"]


async def test_las_rutas_de_consulta_de_polizas_existentes_siguen_funcionando(client):
    response = await client.get("/polizas/mis-polizas", headers=HEADERS)

    assert response.status_code == 200 and response.json() == []
