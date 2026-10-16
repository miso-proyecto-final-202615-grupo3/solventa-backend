import uuid
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.core.config import settings
from src.core.database import Base
from src.application.ports.consentimiento_cache import ConsentimientoCacheEntry
from src.infrastructure.persistence.models import (
    AuditoriaConsentimientoModel,
    ConsentimientoModel,
)
from src.main import app
from src.presentation.dependencies import get_consentimiento_cache, get_db


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
async def consentimiento_client():
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
        yield client, factory
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
    "telefono": "+573001234567",
}


async def test_registro_aceptacion_y_revocacion_auditan_y_bloquean_acceso(
    consentimiento_client,
):
    client, factory = consentimiento_client
    response = await client.post(
        "/api/v1/identity-service/clientes/registro",
        json={**PAYLOAD, "consentimiento_datos": True},
    )
    assert response.status_code == 201
    cliente_id = uuid.UUID(response.json()["id"])

    async with factory() as session:
        consent = await session.scalar(select(ConsentimientoModel))
        audit = await session.scalar(select(AuditoriaConsentimientoModel))
        assert consent.estado == "ACEPTADO"
        assert consent.otorgado_en is not None
        assert audit.tipo_accion == "ACEPTACION"
        assert audit.version_terminos == settings.CONSENT_TERMS_VERSION
        assert audit.canal == "web"

    profile = await client.get(
        f"/api/v1/identity-service/clientes/{cliente_id}/perfil"
    )
    assert profile.status_code == 200
    assert profile.json()["correo"] == PAYLOAD["correo"]

    revoked = await client.put(
        f"/api/v1/identity-service/clientes/{cliente_id}/consentimiento",
        json={"estado": "REVOCADO"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["estado"] == "REVOCADO"

    denied = await client.get(
        f"/api/v1/identity-service/clientes/{cliente_id}/perfil"
    )
    assert denied.status_code == 403

    async with factory() as session:
        consent = await session.scalar(select(ConsentimientoModel))
        revocation = await session.scalar(
            select(AuditoriaConsentimientoModel).where(
                AuditoriaConsentimientoModel.tipo_accion == "REVOCACION"
            )
        )
        assert consent.estado == "REVOCADO"
        assert consent.revocado_en is not None
        assert revocation.version_terminos == settings.CONSENT_TERMS_VERSION
        assert revocation.canal == "web"

    accepted = await client.put(
        f"/api/v1/identity-service/clientes/{cliente_id}/consentimiento",
        json={"estado": "ACEPTADO"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["estado"] == "ACEPTADO"

    profile_after_acceptance = await client.get(
        f"/api/v1/identity-service/clientes/{cliente_id}/perfil"
    )
    assert profile_after_acceptance.status_code == 200

    async with factory() as session:
        consent = await session.scalar(select(ConsentimientoModel))
        audit_count = await session.scalar(
            select(func.count()).select_from(AuditoriaConsentimientoModel)
        )
        assert consent.estado == "ACEPTADO"
        assert consent.revocado_en is None
        assert audit_count == 3


async def test_registro_sin_consentimiento_deniega_consulta_de_perfil(
    consentimiento_client,
):
    client, factory = consentimiento_client
    response = await client.post(
        "/api/v1/identity-service/clientes/registro", json=PAYLOAD
    )
    assert response.status_code == 201
    cliente_id = uuid.UUID(response.json()["id"])

    denied = await client.get(
        f"/api/v1/identity-service/clientes/{cliente_id}/perfil"
    )
    assert denied.status_code == 403

    async with factory() as session:
        consent = await session.scalar(select(ConsentimientoModel))
        audit = await session.scalar(select(AuditoriaConsentimientoModel))
        assert consent.estado == "REVOCADO"
        assert consent.otorgado_en is None
        assert audit.tipo_accion == "DENEGACION"