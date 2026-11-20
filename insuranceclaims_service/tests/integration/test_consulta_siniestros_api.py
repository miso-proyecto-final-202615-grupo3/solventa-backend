"""HU4.2.1: listar los siniestros del cliente (con filtro por póliza) y descargar sus evidencias."""
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
HEADERS = {"X-Cliente-Id": str(CLIENTE), "X-Correlation-Id": "corr-consulta"}
AJENO = {"X-Cliente-Id": str(OTRO_CLIENTE)}
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 96

POLIZA_A = poliza()
POLIZA_B = poliza(poliza_id=uuid.UUID("9e3c7d2f-5b80-4a1f-8b62-1d7c2e0f3a21"), numero="SLV-2026-09999")
POLIZA_AJENA = poliza(
    poliza_id=uuid.UUID("aa3c7d2f-5b80-4a1f-8b62-1d7c2e0f3a99"), numero="SLV-2026-00001", cliente_id=OTRO_CLIENTE
)


@pytest.fixture
async def api(db_session):
    invalidar_cache()
    await sembrar_tipos_siniestro(db_session)
    await db_session.commit()
    almacen = AlmacenEvidenciasEnMemoria(lambda: AHORA)

    async def db_override():
        yield db_session

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_polizas_port] = lambda: PolizasFalsas(POLIZA_A, POLIZA_B, POLIZA_AJENA)
    app.dependency_overrides[get_reloj] = lambda: (lambda: AHORA)
    app.dependency_overrides[get_almacen] = lambda: almacen
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, almacen
    app.dependency_overrides.clear()
    invalidar_cache()


async def _reportar(client, poliza_resumen, headers=HEADERS, ocurrido="2026-11-10T09:00:00-05:00") -> dict:
    response = await client.post(
        f"{BASE}/siniestros",
        json={"poliza_id": str(poliza_resumen.poliza_id), "tipo": "EQUIPAJE",
              "descripcion": "Se perdió la maleta en el aeropuerto.", "ocurrido_en": ocurrido},
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _evidencia_cargada(client, almacen, siniestro_id: str) -> str:
    datos = (await client.post(
        f"{BASE}/siniestros/{siniestro_id}/evidencias",
        json={"tipo": "FOTO", "content_type": "image/jpeg", "tamano_bytes": len(JPEG), "origen": "CAMARA",
              "capturada_en": "2026-11-10T14:35:00-05:00"},
        headers=HEADERS,
    )).json()
    almacen.simular_subida(datos["carga"]["campos"]["key"], JPEG, "image/jpeg")
    confirmada = await client.post(
        f"{BASE}/siniestros/{siniestro_id}/evidencias/{datos['evidencia_id']}/confirmacion", headers=HEADERS
    )
    assert confirmada.json()["estado"] == "CARGADA"
    return datos["evidencia_id"]


# --- Listado --------------------------------------------------------------------------------------

async def test_lista_solo_los_siniestros_del_cliente_y_filtra_por_poliza(api):
    client, _ = api
    a1 = await _reportar(client, POLIZA_A)
    a2 = await _reportar(client, POLIZA_A)
    b1 = await _reportar(client, POLIZA_B)
    await _reportar(client, POLIZA_AJENA, headers=AJENO)

    todos = await client.get(f"{BASE}/siniestros", headers=HEADERS)
    de_a = await client.get(f"{BASE}/siniestros", params={"poliza_id": str(POLIZA_A.poliza_id)}, headers=HEADERS)
    ajena = await client.get(f"{BASE}/siniestros", params={"poliza_id": str(POLIZA_AJENA.poliza_id)}, headers=HEADERS)

    assert todos.status_code == 200
    cuerpo = todos.json()
    assert (cuerpo["pagina"], cuerpo["tamano"], cuerpo["total"]) == (1, 20, 3)
    assert {s["siniestro_id"] for s in cuerpo["siniestros"]} == {a1["siniestro_id"], a2["siniestro_id"], b1["siniestro_id"]}
    assert set(cuerpo["siniestros"][0]) == set(a1)  # mismo resumen que el reporte (sin descripción)
    assert {s["siniestro_id"] for s in de_a.json()["siniestros"]} == {a1["siniestro_id"], a2["siniestro_id"]}
    # La póliza de otro cliente no revela nada: lista vacía, no error.
    assert ajena.status_code == 200 and ajena.json()["siniestros"] == [] and ajena.json()["total"] == 0


async def test_paginacion_y_orden(api):
    client, _ = api
    for _ in range(3):
        await _reportar(client, POLIZA_A)

    primera = (await client.get(f"{BASE}/siniestros", params={"tamano": 2}, headers=HEADERS)).json()
    segunda = (await client.get(f"{BASE}/siniestros", params={"tamano": 2, "pagina": 2}, headers=HEADERS)).json()

    assert (len(primera["siniestros"]), len(segunda["siniestros"]), primera["total"]) == (2, 1, 3)
    ids = [s["siniestro_id"] for s in primera["siniestros"] + segunda["siniestros"]]
    assert len(set(ids)) == 3
    fechas = [s["reportado_en"] for s in primera["siniestros"] + segunda["siniestros"]]
    assert fechas == sorted(fechas, reverse=True)


async def test_sin_siniestros(api):
    client, _ = api

    cuerpo = (await client.get(f"{BASE}/siniestros", headers=HEADERS)).json()

    assert cuerpo == {"siniestros": [], "pagina": 1, "tamano": 20, "total": 0}


@pytest.mark.parametrize(
    "params", [{"pagina": 0}, {"tamano": 0}, {"tamano": 51}, {"poliza_id": "no-es-uuid"}]
)
async def test_parametros_invalidos(api, params):
    client, _ = api

    assert (await client.get(f"{BASE}/siniestros", params=params, headers=HEADERS)).status_code == 422


# --- Descarga de evidencias -----------------------------------------------------------------------

async def test_descarga_de_una_evidencia_cargada(api, caplog):
    client, almacen = api
    caplog.set_level(logging.INFO)
    siniestro_id = (await _reportar(client, POLIZA_A))["siniestro_id"]
    evidencia_id = await _evidencia_cargada(client, almacen, siniestro_id)

    response = await client.get(f"{BASE}/siniestros/{siniestro_id}/evidencias/{evidencia_id}/descarga", headers=HEADERS)

    assert response.status_code == 200
    cuerpo = response.json()
    assert cuerpo["evidencia_id"] == evidencia_id
    assert (cuerpo["tipo"], cuerpo["content_type"], cuerpo["tamano_bytes"]) == ("FOTO", "image/jpeg", len(JPEG))
    assert cuerpo["url"].startswith("https://almacen.test/") and evidencia_id in cuerpo["url"]
    assert cuerpo["expira_en"] == "2026-11-10T20:05:00Z"  # 5 minutos
    assert "almacen.test" not in caplog.text and "firma=" not in caplog.text


async def test_descarga_de_evidencia_pendiente_ajena_o_inexistente(api):
    client, almacen = api
    siniestro_id = (await _reportar(client, POLIZA_A))["siniestro_id"]
    cargada = await _evidencia_cargada(client, almacen, siniestro_id)
    pendiente = (await client.post(
        f"{BASE}/siniestros/{siniestro_id}/evidencias",
        json={"tipo": "FOTO", "content_type": "image/jpeg", "tamano_bytes": 10, "origen": "GALERIA",
              "capturada_en": "2026-11-10T14:35:00-05:00"},
        headers=HEADERS,
    )).json()["evidencia_id"]

    def url(evidencia_id):
        return f"{BASE}/siniestros/{siniestro_id}/evidencias/{evidencia_id}/descarga"

    no_cargada = await client.get(url(pendiente), headers=HEADERS)
    inexistente = await client.get(url(uuid.uuid4()), headers=HEADERS)
    ajena = await client.get(url(cargada), headers=AJENO)

    assert (no_cargada.status_code, no_cargada.json()["detail"]["codigo"]) == (409, "EVIDENCIA_NO_DISPONIBLE")
    assert (inexistente.status_code, inexistente.json()["detail"]["codigo"]) == (404, "EVIDENCIA_NO_ENCONTRADA")
    assert (ajena.status_code, ajena.json()["detail"]["codigo"]) == (404, "SINIESTRO_NO_ENCONTRADO")


async def test_descarga_con_almacen_caido(api):
    client, almacen = api
    siniestro_id = (await _reportar(client, POLIZA_A))["siniestro_id"]
    evidencia_id = await _evidencia_cargada(client, almacen, siniestro_id)
    almacen.caido = True

    response = await client.get(f"{BASE}/siniestros/{siniestro_id}/evidencias/{evidencia_id}/descarga", headers=HEADERS)

    assert (response.status_code, response.json()["detail"]["codigo"]) == (503, "SERVICIO_NO_DISPONIBLE")
