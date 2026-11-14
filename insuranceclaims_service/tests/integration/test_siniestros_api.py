import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from src.infrastructure.persistence.catalogo_tipos_siniestro_impl import invalidar_cache
from src.infrastructure.persistence.seed_tipos_siniestro import sembrar_tipos_siniestro
from src.main import app
from src.presentation.dependencies import get_db, get_polizas_port, get_reloj
from tests.fakes import AHORA, CLIENTE, OTRO_CLIENTE, PolizasFalsas, poliza

BASE = "/api/v1/insuranceclaims-service"
HEADERS = {"X-Cliente-Id": str(CLIENTE), "X-Correlation-Id": "corr-api"}


@pytest.fixture
async def api(db_session):
    invalidar_cache()
    await sembrar_tipos_siniestro(db_session)
    await db_session.commit()
    polizas = PolizasFalsas(poliza())

    async def db_override():
        yield db_session

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_polizas_port] = lambda: polizas
    app.dependency_overrides[get_reloj] = lambda: (lambda: AHORA)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, polizas
    app.dependency_overrides.clear()
    invalidar_cache()


def _body(**cambios) -> dict:
    body = {
        "poliza_id": str(poliza().poliza_id),
        "tipo": "GASTO_MEDICO",
        "descripcion": "  Me atendieron en urgencias durante el viaje.  ",
        "ocurrido_en": "2026-11-10T14:30:00-05:00",
    }
    body.update(cambios)
    return body


def _post(client, body, key=None, headers=HEADERS):
    return client.post(f"{BASE}/siniestros", json=body, headers={**headers, "Idempotency-Key": key or str(uuid.uuid4())})


async def test_polizas_elegibles(api):
    client, polizas = api

    response = await client.get(f"{BASE}/siniestros/polizas-elegibles", headers=HEADERS)

    assert response.status_code == 200
    [p] = response.json()["polizas"]
    assert p["numero"] == "SLV-2026-08341"
    assert p["producto"] == {"codigo": "SEGURO_VIAJE", "nombre": "Seguro de viaje"}
    assert p["vigencia_desde"] == "2026-03-12"
    assert p["tipos_siniestro"][0] == {
        "codigo": "GASTO_MEDICO", "nombre": "Gasto médico", "evidencia": {"fotos_max": 5, "videos_max": 0},
    }
    assert polizas.llamadas == [("listar", "corr-api")]


async def test_polizas_elegibles_en_ingles(api):
    client, _ = api

    response = await client.get(
        f"{BASE}/siniestros/polizas-elegibles", headers={**HEADERS, "Accept-Language": "en-US,en;q=0.9"}
    )

    assert response.json()["polizas"][0]["tipos_siniestro"][0]["nombre"] == "Medical expense"


async def test_reporta_201_y_reintento_200_con_el_mismo_cuerpo(api):
    client, _ = api
    key = str(uuid.uuid4())

    creado = await _post(client, _body(), key)
    repetido = await _post(client, _body(), key)

    assert creado.status_code == 201
    assert repetido.status_code == 200
    assert repetido.json() == creado.json()
    datos = creado.json()
    assert datos["estado"] == "REPORTADO"
    assert datos["numero"].startswith("SIN-2026-")
    assert datos["poliza_numero"] == "SLV-2026-08341"
    assert datos["ocurrido_en"] == "2026-11-10T19:30:00Z"
    assert datos["reportado_en"] == "2026-11-10T20:00:00Z"


async def test_consultar_propio_y_ajeno(api):
    client, _ = api
    creado = (await _post(client, _body())).json()

    propio = await client.get(f"{BASE}/siniestros/{creado['siniestro_id']}", headers=HEADERS)
    ajeno = await client.get(
        f"{BASE}/siniestros/{creado['siniestro_id']}", headers={"X-Cliente-Id": str(OTRO_CLIENTE)}
    )

    assert propio.json() == creado
    assert ajeno.status_code == 404
    assert ajeno.json() == {"detail": {"codigo": "SINIESTRO_NO_ENCONTRADO", "mensaje": "No encontramos el siniestro."}}


@pytest.mark.parametrize(
    ("body", "status", "codigo"),
    [
        (_body(poliza_id=str(uuid.uuid4())), 404, "POLIZA_NO_ENCONTRADA"),
        (_body(tipo="ROBO"), 422, "TIPO_NO_PERMITIDO"),
        (_body(ocurrido_en="2026-01-01T10:00:00-05:00"), 409, "FECHA_FUERA_DE_VIGENCIA"),
        (_body(ocurrido_en="2026-11-11T10:00:00-05:00"), 422, "FECHA_INVALIDA"),
    ],
)
async def test_errores_de_negocio(api, body, status, codigo):
    client, _ = api

    response = await _post(client, body)

    assert response.status_code == status
    assert response.json()["detail"]["codigo"] == codigo


async def test_misma_clave_con_otros_datos_es_409(api):
    client, _ = api
    key = str(uuid.uuid4())
    await _post(client, _body(), key)

    response = await _post(client, _body(descripcion="Otra descripción del evento."), key)

    assert response.status_code == 409
    assert response.json()["detail"]["codigo"] == "IDEMPOTENCIA_CONFLICTO"


@pytest.mark.parametrize(
    "body",
    [
        _body(descripcion="corta"),
        _body(descripcion="x" * 501),
        _body(ocurrido_en="2026-11-10T14:30:00"),
        _body(tipo="gasto medico"),
        {**_body(), "cliente_id": str(CLIENTE)},
    ],
)
async def test_validacion_de_entrada_422(api, body):
    client, _ = api

    assert (await _post(client, body)).status_code == 422


async def test_sin_cliente_o_sin_clave_es_422(api):
    client, _ = api

    sin_cliente = await client.post(
        f"{BASE}/siniestros", json=_body(), headers={"Idempotency-Key": str(uuid.uuid4())}
    )
    clave_invalida = await client.post(
        f"{BASE}/siniestros", json=_body(), headers={**HEADERS, "Idempotency-Key": "no-es-uuid"}
    )

    assert sin_cliente.status_code == 422
    assert clave_invalida.status_code == 422


async def test_polizas_caido_es_503(api):
    client, polizas = api
    polizas.caido = True

    response = await client.get(f"{BASE}/siniestros/polizas-elegibles", headers=HEADERS)

    assert response.status_code == 503
    assert response.json()["detail"]["codigo"] == "SERVICIO_NO_DISPONIBLE"


async def test_catalogo_de_tipos_para_otros_consumidores(api):
    client, _ = api

    todos = await client.get(f"{BASE}/tipos-siniestro")
    dispositivos = await client.get(f"{BASE}/tipos-siniestro", params={"producto_codigo": "PROTECCION_DISPOSITIVOS"})
    vida = await client.get(f"{BASE}/tipos-siniestro", params={"producto_codigo": "VIDA_HIPOTECARIO"})

    assert len(todos.json()["tipos"]) == 5
    assert [t["codigo"] for t in dispositivos.json()["tipos"]] == ["DANO_DISPOSITIVO", "ROBO"]
    assert dispositivos.json()["tipos"][1]["producto_codigo"] == "PROTECCION_DISPOSITIVOS"
    assert vida.json() == {"tipos": []}
