import uuid
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.ports.consentimiento_cache import ConsentimientoCacheEntry
from src.core.config import settings
from src.core.database import Base
from src.main import app
from src.presentation.dependencies import get_consentimiento_cache, get_db

BASE = "/api/v1/identity-service"


class InMemoryConsentimientoCache:
    def __init__(self):
        self.entries: dict[uuid.UUID, ConsentimientoCacheEntry] = {}

    async def obtener(self, cliente_id: uuid.UUID):
        return self.entries.get(cliente_id)

    async def guardar(self, cliente_id, estado, perfil):
        self.entries[cliente_id] = ConsentimientoCacheEntry(estado, perfil)

    async def invalidar(self, cliente_id: uuid.UUID):
        self.entries.pop(cliente_id, None)


@pytest.fixture
async def auditoria_client():
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

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_consentimiento_cache] = InMemoryConsentimientoCache
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
    app.dependency_overrides.clear()
    await engine.dispose()


PAYLOAD = {
    "nombres": "Ana",
    "apellidos": "Pérez",
    "tipo_documento": "CC",
    "numero_identificacion": "1020304050",
    "correo": "ana.perez@example.com",
    "password": "Secreta123",
    "fecha_nacimiento": date(1990, 5, 15).isoformat(),
    "pais_residencia": "Colombia",
    "telefono": "3001234567",
}


async def _registrar(client, **cambios) -> uuid.UUID:
    response = await client.post(
        f"{BASE}/clientes/registro", json={**PAYLOAD, **cambios}
    )
    assert response.status_code == 201
    return uuid.UUID(response.json()["id"])


async def test_consulta_por_correo_ignora_mayusculas_y_devuelve_el_log(auditoria_client):
    cliente_id = await _registrar(auditoria_client, consentimiento_datos=True)

    response = await auditoria_client.get(
        f"{BASE}/consentimientos", params={"correo": "ANA.PEREZ@example.com"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["cliente"]["id"] == str(cliente_id)
    assert body["cliente"]["correo"] == PAYLOAD["correo"]
    assert body["cliente"]["estado_consentimiento"] == "ACEPTADO"
    assert len(body["eventos"]) == 1
    evento = body["eventos"][0]
    assert evento["tipo_accion"] == "ACEPTACION"
    assert evento["version_terminos"] == settings.CONSENT_TERMS_VERSION
    assert evento["canal"] == "web"
    assert evento["fecha"]


async def test_consulta_por_identificacion(auditoria_client):
    cliente_id = await _registrar(auditoria_client, consentimiento_datos=True)

    response = await auditoria_client.get(
        f"{BASE}/consentimientos",
        params={"identificacion": PAYLOAD["numero_identificacion"]},
    )

    assert response.status_code == 200
    assert response.json()["cliente"]["id"] == str(cliente_id)


async def test_los_eventos_salen_por_fecha_descendente(auditoria_client):
    cliente_id = await _registrar(auditoria_client, consentimiento_datos=True)
    revocado = await auditoria_client.put(
        f"{BASE}/clientes/{cliente_id}/consentimiento", json={"estado": "REVOCADO"}
    )
    assert revocado.status_code == 200

    response = await auditoria_client.get(
        f"{BASE}/consentimientos", params={"correo": PAYLOAD["correo"]}
    )

    body = response.json()
    assert [e["tipo_accion"] for e in body["eventos"]] == ["REVOCACION", "ACEPTACION"]
    assert body["cliente"]["estado_consentimiento"] == "REVOCADO"


async def test_registro_sin_consentimiento_queda_auditado_como_denegacion(auditoria_client):
    await _registrar(auditoria_client, consentimiento_datos=False)

    response = await auditoria_client.get(
        f"{BASE}/consentimientos", params={"correo": PAYLOAD["correo"]}
    )

    body = response.json()
    assert [e["tipo_accion"] for e in body["eventos"]] == ["DENEGACION"]
    assert body["cliente"]["estado_consentimiento"] == "REVOCADO"


async def test_cliente_inexistente_devuelve_404(auditoria_client):
    response = await auditoria_client.get(
        f"{BASE}/consentimientos", params={"correo": "nadie@example.com"}
    )

    assert response.status_code == 404


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"correo": "a@example.com", "identificacion": "12345"},
        {"correo": "  "},
    ],
)
async def test_exige_exactamente_un_criterio(auditoria_client, params):
    response = await auditoria_client.get(f"{BASE}/consentimientos", params=params)

    assert response.status_code == 422


@pytest.mark.parametrize("metodo", ["POST", "PUT", "PATCH", "DELETE"])
async def test_la_auditoria_es_de_solo_lectura(auditoria_client, metodo):
    response = await auditoria_client.request(
        metodo, f"{BASE}/consentimientos", params={"correo": PAYLOAD["correo"]}
    )

    assert response.status_code == 405
