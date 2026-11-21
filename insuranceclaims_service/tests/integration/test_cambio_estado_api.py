"""HU4.2.2 · Cambio de estado por operador (N6, N7): token, transiciones y evento en el outbox."""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.core.config import settings
from src.infrastructure.persistence.catalogo_tipos_siniestro_impl import invalidar_cache
from src.infrastructure.persistence.models import EventoOutboxModel, SiniestroModel
from src.infrastructure.persistence.seed_tipos_siniestro import sembrar_tipos_siniestro
from src.main import app
from src.presentation.dependencies import get_db, get_polizas_port, get_reloj
from tests.fakes import AHORA, CLIENTE, PolizasFalsas, poliza

BASE = "/api/v1/insuranceclaims-service"
TOKEN = "token-operador-de-prueba"
OPERADOR = {"X-Operador-Token": TOKEN}


@pytest.fixture
async def api(db_session, monkeypatch):
    monkeypatch.setattr(settings, "OPERADOR_TOKEN", TOKEN)
    invalidar_cache()
    await sembrar_tipos_siniestro(db_session)
    await db_session.commit()

    async def db_override():
        yield db_session

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_polizas_port] = lambda: PolizasFalsas(poliza())
    app.dependency_overrides[get_reloj] = lambda: (lambda: AHORA)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        creado = await client.post(
            f"{BASE}/siniestros",
            json={"poliza_id": str(poliza().poliza_id), "tipo": "EQUIPAJE",
                  "descripcion": "Se perdió la maleta en el aeropuerto.", "ocurrido_en": "2026-11-10T09:00:00-05:00"},
            headers={"X-Cliente-Id": str(CLIENTE), "Idempotency-Key": str(uuid.uuid4())},
        )
        yield client, db_session, creado.json()["siniestro_id"]
    app.dependency_overrides.clear()
    invalidar_cache()


async def _eventos(db) -> list[EventoOutboxModel]:
    return list((await db.scalars(select(EventoOutboxModel))).all())


async def test_cambio_valido_escribe_un_evento_en_el_outbox(api):
    client, db, siniestro_id = api

    response = await client.put(f"{BASE}/siniestros/{siniestro_id}/estado", json={"estado": "EN_EVALUACION"}, headers=OPERADOR)

    assert response.status_code == 200
    assert response.json()["estado"] == "EN_EVALUACION"
    eventos = await _eventos(db)
    assert len(eventos) == 1
    evento = eventos[0]
    assert (evento.tipo, evento.estado, str(evento.agregado_id)) == ("SINIESTRO_ESTADO", "PENDIENTE", siniestro_id)
    assert evento.payload == {
        "tipo": "SINIESTRO_ESTADO", "siniestro_id": siniestro_id,
        "numero": response.json()["numero"], "estado": "EN_EVALUACION",
    }
    guardado = await db.get(SiniestroModel, uuid.UUID(siniestro_id))
    assert guardado.estado_actualizado_en is not None


async def test_el_mismo_estado_responde_200_sin_evento(api):
    client, db, siniestro_id = api

    response = await client.put(f"{BASE}/siniestros/{siniestro_id}/estado", json={"estado": "REPORTADO"}, headers=OPERADOR)

    assert response.status_code == 200
    assert await _eventos(db) == []


async def test_transicion_invalida(api):
    client, db, siniestro_id = api

    response = await client.put(f"{BASE}/siniestros/{siniestro_id}/estado", json={"estado": "PAGADO"}, headers=OPERADOR)

    assert (response.status_code, response.json()["detail"]["codigo"]) == (409, "TRANSICION_INVALIDA")
    assert await _eventos(db) == []


@pytest.mark.parametrize("headers", [{}, {"X-Operador-Token": "otro"}])
async def test_sin_token_de_operador_valido(api, headers):
    client, db, siniestro_id = api

    response = await client.put(f"{BASE}/siniestros/{siniestro_id}/estado", json={"estado": "EN_EVALUACION"}, headers=headers)

    assert response.status_code == 403
    assert await _eventos(db) == []


async def test_sin_token_configurado_siempre_403(api, monkeypatch):
    client, _, siniestro_id = api
    monkeypatch.setattr(settings, "OPERADOR_TOKEN", "")

    response = await client.put(f"{BASE}/siniestros/{siniestro_id}/estado", json={"estado": "EN_EVALUACION"}, headers={"X-Operador-Token": ""})

    assert response.status_code == 403


async def test_siniestro_inexistente_y_estado_desconocido(api):
    client, _, siniestro_id = api

    inexistente = await client.put(f"{BASE}/siniestros/{uuid.uuid4()}/estado", json={"estado": "EN_EVALUACION"}, headers=OPERADOR)
    desconocido = await client.put(f"{BASE}/siniestros/{siniestro_id}/estado", json={"estado": "CERRADO"}, headers=OPERADOR)

    assert (inexistente.status_code, inexistente.json()["detail"]["codigo"]) == (404, "SINIESTRO_NO_ENCONTRADO")
    assert desconocido.status_code == 422
