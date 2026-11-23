"""HU4.2.2 · Tokens push internos: registrar, reasignar (CA3), destinos solo ACTIVO, borrar y token fuera de la URL."""
import logging
import uuid
from datetime import date

import pytest

from src.infrastructure.persistence.models import ClienteModel, DispositivoVinculadoModel
from src.main import app
from src.presentation.dependencies import get_db

BASE = "/api/v1/identity-service/clientes"
TOKEN = "fcm-token-" + "a" * 120 + "AB12CD"


async def _cliente(db, correo: str) -> ClienteModel:
    cliente = ClienteModel(
        nombres="Ana", apellidos="Pérez", tipo_documento="CC", numero_identificacion=str(uuid.uuid4().int)[:10],
        correo=correo, fecha_nacimiento=date(1990, 1, 1), pais_residencia="Colombia", telefono="+573001234567",
    )
    db.add(cliente)
    await db.flush()
    return cliente


async def _dispositivo(db, cliente: ClienteModel, estado: str = "ACTIVO") -> uuid.UUID:
    installation_id = uuid.uuid4()
    db.add(DispositivoVinculadoModel(
        cliente_id=cliente.id, installation_id=installation_id, plataforma="ANDROID",
        modelo="Pixel", version_so="14", folio_verificacion=f"folio-{installation_id}", estado=estado,
    ))
    await db.flush()
    return installation_id


@pytest.fixture
async def api(async_client, db_session):
    async def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    yield async_client, db_session
    app.dependency_overrides.pop(get_db, None)


async def test_registra_y_lista_el_destino_del_dispositivo_activo(api, caplog):
    client, db = api
    caplog.set_level(logging.INFO)
    ana = await _cliente(db, "ana@example.com")
    instalacion = await _dispositivo(db, ana)
    await db.commit()

    registro = await client.put(f"{BASE}/{ana.id}/dispositivos/{instalacion}/push", json={"token": TOKEN, "plataforma": "ANDROID"})
    otra_vez = await client.put(f"{BASE}/{ana.id}/dispositivos/{instalacion}/push", json={"token": TOKEN, "plataforma": "ANDROID"})
    destinos = await client.get(f"{BASE}/{ana.id}/destinos-push")

    assert (registro.status_code, otra_vez.status_code) == (204, 204)
    assert destinos.json() == {"destinos": [{"installation_id": str(instalacion), "token": TOKEN, "plataforma": "ANDROID"}]}
    assert TOKEN not in caplog.text


async def test_dispositivo_no_vinculado_o_revocado(api):
    client, db = api
    ana = await _cliente(db, "ana2@example.com")
    revocado = await _dispositivo(db, ana, estado="REVOCADO")
    await db.commit()

    for instalacion in (revocado, uuid.uuid4()):
        response = await client.put(f"{BASE}/{ana.id}/dispositivos/{instalacion}/push", json={"token": TOKEN, "plataforma": "ANDROID"})
        assert (response.status_code, response.json()["detail"]["codigo"]) == (404, "DISPOSITIVO_NO_VINCULADO")


async def test_el_token_registrado_por_otro_cliente_deja_de_ser_del_anterior(api):
    client, db = api
    ana = await _cliente(db, "ana3@example.com")
    beto = await _cliente(db, "beto@example.com")
    de_ana = await _dispositivo(db, ana)
    de_beto = await _dispositivo(db, beto)
    await db.commit()

    await client.put(f"{BASE}/{ana.id}/dispositivos/{de_ana}/push", json={"token": TOKEN, "plataforma": "ANDROID"})
    await client.put(f"{BASE}/{beto.id}/dispositivos/{de_beto}/push", json={"token": TOKEN, "plataforma": "ANDROID"})

    assert (await client.get(f"{BASE}/{ana.id}/destinos-push")).json() == {"destinos": []}
    assert [d["installation_id"] for d in (await client.get(f"{BASE}/{beto.id}/destinos-push")).json()["destinos"]] == [str(de_beto)]


async def test_borrar_al_cerrar_sesion_y_token_invalido_sin_token_en_la_url(api):
    client, db = api
    ana = await _cliente(db, "ana4@example.com")
    uno = await _dispositivo(db, ana)
    await db.commit()
    await client.put(f"{BASE}/{ana.id}/dispositivos/{uno}/push", json={"token": TOKEN, "plataforma": "ANDROID"})

    invalido = await client.post(f"{BASE}/destinos-push/eliminacion", json={"token": TOKEN})
    assert invalido.status_code == 204
    assert (await client.get(f"{BASE}/{ana.id}/destinos-push")).json() == {"destinos": []}

    await client.put(f"{BASE}/{ana.id}/dispositivos/{uno}/push", json={"token": TOKEN, "plataforma": "ANDROID"})
    cierre = await client.delete(f"{BASE}/{ana.id}/dispositivos/{uno}/push")
    repetido = await client.delete(f"{BASE}/{ana.id}/dispositivos/{uno}/push")
    assert (cierre.status_code, repetido.status_code) == (204, 204)
    assert (await client.get(f"{BASE}/{ana.id}/destinos-push")).json() == {"destinos": []}


@pytest.mark.parametrize(
    "body", [{"token": "", "plataforma": "ANDROID"}, {"token": "t", "plataforma": "IOS"}, {"token": "x" * 1025, "plataforma": "ANDROID"}]
)
async def test_validacion_del_registro(api, body):
    client, db = api
    ana = await _cliente(db, f"ana-{uuid.uuid4().hex[:6]}@example.com")
    instalacion = await _dispositivo(db, ana)
    await db.commit()

    assert (await client.put(f"{BASE}/{ana.id}/dispositivos/{instalacion}/push", json=body)).status_code == 422
