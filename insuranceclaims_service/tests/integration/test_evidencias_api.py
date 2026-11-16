import logging
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from src.infrastructure.persistence.catalogo_tipos_siniestro_impl import invalidar_cache
from src.infrastructure.persistence.seed_tipos_siniestro import sembrar_tipos_siniestro
from src.infrastructure.storage.memoria import AlmacenEvidenciasEnMemoria
from src.main import app
from src.presentation.dependencies import get_almacen, get_db, get_polizas_port, get_reloj
from tests.fakes import AHORA, CLIENTE, OTRO_CLIENTE, PolizasFalsas, poliza

BASE = "/api/v1/insuranceclaims-service"
HEADERS = {"X-Cliente-Id": str(CLIENTE), "X-Correlation-Id": "corr-evid"}
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 96


@pytest.fixture
async def api(db_session):
    invalidar_cache()
    await sembrar_tipos_siniestro(db_session)
    await db_session.commit()
    almacen = AlmacenEvidenciasEnMemoria(lambda: AHORA)

    async def db_override():
        yield db_session

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_polizas_port] = lambda: PolizasFalsas(poliza())
    app.dependency_overrides[get_reloj] = lambda: (lambda: AHORA)
    app.dependency_overrides[get_almacen] = lambda: almacen
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        creado = await client.post(
            f"{BASE}/siniestros",
            json={"poliza_id": str(poliza().poliza_id), "tipo": "EQUIPAJE",
                  "descripcion": "Se perdió la maleta en el aeropuerto.", "ocurrido_en": "2026-11-10T09:00:00-05:00"},
            headers={**HEADERS, "Idempotency-Key": str(uuid.uuid4())},
        )
        yield client, almacen, creado.json()["siniestro_id"]
    app.dependency_overrides.clear()
    invalidar_cache()


def _solicitud(**cambios) -> dict:
    datos = {"tipo": "FOTO", "content_type": "image/jpeg", "tamano_bytes": len(JPEG), "origen": "CAMARA",
             "capturada_en": "2026-11-10T14:35:00-05:00"}
    datos.update(cambios)
    return datos


async def test_flujo_solicitar_subir_confirmar_y_detalle(api, caplog):
    client, almacen, siniestro_id = api
    caplog.set_level(logging.INFO)

    solicitud = await client.post(f"{BASE}/siniestros/{siniestro_id}/evidencias", json=_solicitud(), headers=HEADERS)
    assert solicitud.status_code == 201
    datos = solicitud.json()
    assert datos["estado"] == "PENDIENTE"
    assert datos["carga"]["tamano_max_bytes"] == 5 * 1024 * 1024
    assert datos["carga"]["expira_en"] == "2026-11-10T20:10:00Z"

    almacen.simular_subida(datos["carga"]["campos"]["key"], JPEG, "image/jpeg")
    confirmada = await client.post(
        f"{BASE}/siniestros/{siniestro_id}/evidencias/{datos['evidencia_id']}/confirmacion", headers=HEADERS
    )
    ubicacion = await client.put(
        f"{BASE}/siniestros/{siniestro_id}/ubicacion",
        json={"latitud": 4.6533, "longitud": -74.0836, "precision_m": 18.5, "fuente": "GPS",
              "capturada_en": "2026-11-10T14:36:10-05:00"},
        headers=HEADERS,
    )
    detalle = await client.get(f"{BASE}/siniestros/{siniestro_id}", headers=HEADERS)

    assert confirmada.status_code == 200
    assert confirmada.json()["estado"] == "CARGADA"
    assert confirmada.json()["cargada_en"] == "2026-11-10T20:00:00Z"
    assert ubicacion.status_code == 200
    assert ubicacion.json()["ubicacion"]["fuente"] == "GPS"
    cuerpo = detalle.json()
    assert cuerpo["ubicacion"]["latitud"] == pytest.approx(4.6533)
    assert [e["estado"] for e in cuerpo["evidencias"]] == ["CARGADA"]
    # Sin URL firmadas ni coordenadas en los logs.
    assert "policy" not in caplog.text and "almacen.test" not in caplog.text and "4.6533" not in caplog.text


@pytest.mark.parametrize(
    ("cambios", "status", "codigo"),
    [
        ({"content_type": "image/png"}, 415, "FORMATO_NO_SOPORTADO"),
        ({"tamano_bytes": 5 * 1024 * 1024 + 1}, 413, "EVIDENCIA_DEMASIADO_GRANDE"),
        ({"capturada_en": "2026-11-11T14:35:00-05:00"}, 422, "FECHA_INVALIDA"),
    ],
)
async def test_errores_de_la_solicitud(api, cambios, status, codigo):
    client, _, siniestro_id = api

    response = await client.post(f"{BASE}/siniestros/{siniestro_id}/evidencias", json=_solicitud(**cambios), headers=HEADERS)

    assert response.status_code == status
    assert response.json()["detail"]["codigo"] == codigo


async def test_limite_de_videos(api):
    client, _, siniestro_id = api
    video = _solicitud(tipo="VIDEO", content_type="video/mp4", tamano_bytes=1000)

    primera = await client.post(f"{BASE}/siniestros/{siniestro_id}/evidencias", json=video, headers=HEADERS)
    segunda = await client.post(f"{BASE}/siniestros/{siniestro_id}/evidencias", json=video, headers=HEADERS)

    assert primera.status_code == 201
    assert segunda.status_code == 409
    assert segunda.json()["detail"]["codigo"] == "LIMITE_EVIDENCIAS"


@pytest.mark.parametrize(
    "body",
    [_solicitud(tamano_bytes=0), _solicitud(tipo="AUDIO"), _solicitud(origen="WEB"), {**_solicitud(), "url": "x"},
     _solicitud(capturada_en="2026-11-10T14:35:00")],
)
async def test_validacion_de_la_solicitud(api, body):
    client, _, siniestro_id = api

    assert (await client.post(f"{BASE}/siniestros/{siniestro_id}/evidencias", json=body, headers=HEADERS)).status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        {"latitud": 91, "longitud": 0, "precision_m": 10, "fuente": "GPS", "capturada_en": "2026-11-10T14:00:00Z"},
        {"latitud": 4, "longitud": 0, "precision_m": 0, "fuente": "GPS", "capturada_en": "2026-11-10T14:00:00Z"},
        {"latitud": 4, "longitud": 0, "precision_m": 10, "fuente": "SATELITE", "capturada_en": "2026-11-10T14:00:00Z"},
    ],
)
async def test_ubicacion_invalida(api, body):
    client, _, siniestro_id = api

    assert (await client.put(f"{BASE}/siniestros/{siniestro_id}/ubicacion", json=body, headers=HEADERS)).status_code == 422


async def test_siniestro_ajeno(api):
    client, _, siniestro_id = api
    ajeno = {"X-Cliente-Id": str(OTRO_CLIENTE)}

    solicitud = await client.post(f"{BASE}/siniestros/{siniestro_id}/evidencias", json=_solicitud(), headers=ajeno)
    confirmacion = await client.post(f"{BASE}/siniestros/{siniestro_id}/evidencias/{uuid.uuid4()}/confirmacion", headers=ajeno)

    assert solicitud.json()["detail"]["codigo"] == "SINIESTRO_NO_ENCONTRADO"
    assert confirmacion.json()["detail"]["codigo"] == "EVIDENCIA_NO_ENCONTRADA"


async def test_confirmar_sin_subir_y_almacen_caido(api):
    client, almacen, siniestro_id = api
    datos = (await client.post(f"{BASE}/siniestros/{siniestro_id}/evidencias", json=_solicitud(), headers=HEADERS)).json()
    url = f"{BASE}/siniestros/{siniestro_id}/evidencias/{datos['evidencia_id']}/confirmacion"

    sin_subir = await client.post(url, headers=HEADERS)
    almacen.caido = True
    caido = await client.post(url, headers=HEADERS)

    assert (sin_subir.status_code, sin_subir.json()["detail"]["codigo"]) == (409, "CARGA_NO_ENCONTRADA")
    assert (caido.status_code, caido.json()["detail"]["codigo"]) == (503, "SERVICIO_NO_DISPONIBLE")


async def test_reintento_con_la_misma_idempotency_key(api):
    client, almacen, siniestro_id = api
    headers = {**HEADERS, "Idempotency-Key": str(uuid.uuid4())}
    url = f"{BASE}/siniestros/{siniestro_id}/evidencias"

    primera = await client.post(url, json=_solicitud(), headers=headers)
    segunda = await client.post(url, json=_solicitud(), headers=headers)
    assert (primera.status_code, segunda.status_code) == (201, 200)
    assert segunda.json()["evidencia_id"] == primera.json()["evidencia_id"]

    almacen.simular_subida(segunda.json()["carga"]["campos"]["key"], JPEG, "image/jpeg")
    await client.post(f"{url}/{primera.json()['evidencia_id']}/confirmacion", headers=HEADERS)
    tercera = await client.post(url, json=_solicitud(), headers=headers)

    assert tercera.status_code == 200
    assert tercera.json()["estado"] == "CARGADA" and tercera.json()["carga"] is None


async def test_idempotency_key_que_no_es_uuid(api):
    client, _, siniestro_id = api

    response = await client.post(
        f"{BASE}/siniestros/{siniestro_id}/evidencias", json=_solicitud(), headers={**HEADERS, "Idempotency-Key": "x"}
    )

    assert response.status_code in (400, 422)
