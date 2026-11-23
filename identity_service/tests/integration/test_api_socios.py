from cryptography.fernet import Fernet
import pytest
from sqlalchemy import select

from src.core.config import settings
from src.infrastructure.persistence.models import ClienteSocioModel, EventoSocioModel, SocioApiKeyModel
from src.main import app
from src.presentation.dependencies import get_consentimiento_cache, get_db, get_identity_provider

BASE = "/api/v1/identity-service/socios"
PROSPECTO = {
    "nombres": "Ana",
    "apellidos": "Perez",
    "tipo_documento": "CC",
    "numero_identificacion": "1020304050",
    "correo": "ana@example.com",
    "fecha_nacimiento": "1990-05-15",
    "pais_residencia": "Colombia",
    "telefono": "+573001234567",
    "consentimiento_datos": True,
}


@pytest.fixture
async def cliente_socios(async_client, db_session, fake_identity_provider, fake_consentimiento_cache, monkeypatch):
    async def override_db():
        yield db_session

    monkeypatch.setattr(settings, "SOCIOS_API_KEY_ENCRYPTION_KEY", Fernet.generate_key().decode())
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_identity_provider] = lambda: fake_identity_provider
    app.dependency_overrides[get_consentimiento_cache] = lambda: fake_consentimiento_cache
    yield async_client, db_session, fake_identity_provider
    app.dependency_overrides.clear()


async def _crear_socio(client, email):
    response = await client.post(BASE, headers={"X-Actor-Id": "admin"}, json={
        "nombre": "Banco", "correo": email, "tipo_socio": "Banco", "canal_integracion": "API",
    })
    assert response.status_code == 201
    return response.json()["id"]


async def test_ciclo_de_api_keys(cliente_socios):
    client, db, _ = cliente_socios
    socio = await _crear_socio(client, "socio@example.com")
    response = await client.post(
        f"{BASE}/{socio}/api-keys", headers={"X-Actor-Id": "operator-123"}
    )
    assert response.status_code == 201
    creada = response.json()
    assert set(creada) == {"api_key_id", "fecha_generacion", "api_key"}
    key = creada["api_key"]
    row = (await db.scalars(select(SocioApiKeyModel))).one()
    assert key not in row.valor_cifrado
    assert Fernet(settings.SOCIOS_API_KEY_ENCRYPTION_KEY.encode()).decrypt(row.valor_cifrado.encode()).decode() == key
    evento = (await db.scalars(select(EventoSocioModel))).all()[-1]
    assert evento.accion == "CREDENCIAL_GENERADA"
    assert evento.actor_id == "operator-123"
    assert (await client.post(f"{BASE}/validar-api-key", json={"api_key": key})).json() == {"socio_id": socio}
    listado = (await client.get(f"{BASE}/{socio}/api-keys")).json()
    assert listado == [{"api_key_id": creada["api_key_id"], "fecha_generacion": creada["fecha_generacion"]}]
    assert (await client.get(f"{BASE}/{socio}/api-keys/{creada['api_key_id']}")).json() == listado[0]
    assert (await client.delete(f"{BASE}/{socio}/api-keys/{creada['api_key_id']}")).status_code == 204
    assert (await client.post(f"{BASE}/validar-api-key", json={"api_key": key})).status_code == 401


async def test_prospecto_nuevo_y_asociacion_idempotente(cliente_socios):
    client, db, provider = cliente_socios
    socio = await _crear_socio(client, "socio1@example.com")
    otro = await _crear_socio(client, "socio2@example.com")
    first = await client.post(f"{BASE}/{socio}/prospectos", json=PROSPECTO)
    assert first.status_code == 201
    cliente = first.json()["id"]
    assert provider.registrados == [("ana@example.com", "solv1020304050")]
    assert (await client.get(f"{BASE}/{socio}/clientes/{cliente}/autorizacion")).status_code == 204
    assert (await client.get(f"{BASE}/{otro}/clientes/{cliente}/autorizacion")).status_code == 403
    for socio_id in (socio, otro, otro):
        response = await client.post(f"{BASE}/{socio_id}/prospectos", json=PROSPECTO)
        assert response.status_code == 201
        assert response.json()["id"] == cliente
    assert len(provider.registrados) == 1
    assert len((await db.scalars(select(ClienteSocioModel))).all()) == 2
    conflicting = {**PROSPECTO, "numero_identificacion": "1234567890"}
    assert (await client.post(f"{BASE}/{otro}/prospectos", json=conflicting)).status_code == 409


async def test_api_key_sin_clave_de_cifrado_falla(cliente_socios, monkeypatch):
    client, _, _ = cliente_socios
    socio = await _crear_socio(client, "socio@example.com")
    monkeypatch.setattr(settings, "SOCIOS_API_KEY_ENCRYPTION_KEY", "")
    assert (
        await client.post(
            f"{BASE}/{socio}/api-keys", headers={"X-Actor-Id": "operator-123"}
        )
    ).status_code == 503


async def test_asocia_cliente_registrado_en_web_sin_cambiar_su_identidad(cliente_socios):
    client, _, provider = cliente_socios
    socio = await _crear_socio(client, "socio@example.com")
    web = await client.post("/api/v1/identity-service/clientes/registro", json={**PROSPECTO, "password": "Secreta123"})
    assert web.status_code == 201
    asociado = await client.post(f"{BASE}/{socio}/prospectos", json=PROSPECTO)
    assert asociado.status_code == 201
    assert asociado.json()["id"] == web.json()["id"]
    assert provider.registrados == [("ana@example.com", "Secreta123")]
    assert (await client.get(f"{BASE}/{socio}/clientes/{web.json()['id']}/autorizacion")).status_code == 204


async def test_error_de_identidad_no_crea_prospecto_ni_asociacion(cliente_socios):
    client, db, provider = cliente_socios
    socio = await _crear_socio(client, "socio@example.com")
    provider.fallar_registro = True
    response = await client.post(f"{BASE}/{socio}/prospectos", json=PROSPECTO)
    assert response.status_code == 503
    assert not (await db.scalars(select(ClienteSocioModel))).all()
    assert (await client.post(f"{BASE}/{socio}/prospectos", json={**PROSPECTO, "password": "no-admitida"})).status_code == 422
