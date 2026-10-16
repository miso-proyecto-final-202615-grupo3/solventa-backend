import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.core.database import Base
from src.main import app
from src.presentation.dependencies import (
    get_consentimiento_cache,
    get_db,
    get_identity_provider,
)

PAYLOAD = {
    "nombres": "Ana",
    "apellidos": "Pérez",
    "tipo_documento": "CC",
    "numero_identificacion": "1020304050",
    "correo": "ana.perez@example.com",
    "password": "Secreta123",
    "fecha_nacimiento": "1990-05-15",
    "pais_residencia": "Colombia",
    "telefono": "+573001234567",
}


@pytest.fixture
async def registro_client(fake_identity_provider, fake_consentimiento_cache):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_identity_provider] = lambda: fake_identity_provider
    app.dependency_overrides[get_consentimiento_cache] = (
        lambda: fake_consentimiento_cache
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, fake_identity_provider

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
async def registro_local_client(fake_consentimiento_cache):
    """Usa la BD local y deja el proveedor de identidad por defecto (Noop)."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_consentimiento_cache] = (
        lambda: fake_consentimiento_cache
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client

    app.dependency_overrides.clear()
    await engine.dispose()


async def test_registro_local_devuelve_201_sin_cognito(registro_local_client):
    response = await registro_local_client.post(
        "/api/v1/identity-service/clientes/registro", json=PAYLOAD
    )

    assert response.status_code == 201
    data = response.json()
    assert data["correo"] == PAYLOAD["correo"]
    assert data["estado_kyc"] == "PENDIENTE"


async def test_registro_exitoso(registro_client):
    client, fake = registro_client

    response = await client.post(
        "/api/v1/identity-service/clientes/registro", json=PAYLOAD
    )

    assert response.status_code == 201
    data = response.json()
    assert data["correo"] == PAYLOAD["correo"]
    assert data["tipo_documento"] == "CC"
    assert data["estado_kyc"] == "PENDIENTE"
    assert "password" not in data
    assert fake.registrados == [(PAYLOAD["correo"], PAYLOAD["password"])]


async def test_registro_rechaza_correo_duplicado(registro_client):
    client, fake = registro_client
    first = await client.post(
        "/api/v1/identity-service/clientes/registro", json=PAYLOAD
    )
    assert first.status_code == 201

    dup = {
        **PAYLOAD,
        "numero_identificacion": "555555555",
        "password": "OtraClave1",
    }
    response = await client.post(
        "/api/v1/identity-service/clientes/registro", json=dup
    )

    assert response.status_code == 409
    assert len(fake.registrados) == 1


async def test_registro_rechaza_documento_duplicado(registro_client):
    client, fake = registro_client
    first = await client.post(
        "/api/v1/identity-service/clientes/registro", json=PAYLOAD
    )
    assert first.status_code == 201

    dup = {
        **PAYLOAD,
        "correo": "luis.gomez@example.com",
        "password": "OtraClave1",
    }
    response = await client.post(
        "/api/v1/identity-service/clientes/registro", json=dup
    )

    assert response.status_code == 409
    assert len(fake.registrados) == 1


async def test_registro_rechaza_payload_invalido(registro_client):
    client, _ = registro_client
    invalid = {**PAYLOAD, "correo": "no-es-correo"}

    response = await client.post(
        "/api/v1/identity-service/clientes/registro", json=invalid
    )

    assert response.status_code == 422


async def test_registro_devuelve_503_si_identidad_falla(registro_client):
    client, fake = registro_client
    fake.fallar_registro = True

    response = await client.post(
        "/api/v1/identity-service/clientes/registro", json=PAYLOAD
    )

    assert response.status_code == 503