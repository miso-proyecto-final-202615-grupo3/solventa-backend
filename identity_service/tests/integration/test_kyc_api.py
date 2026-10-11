import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.ports.kyc import KycVerifier
from src.core.database import Base
from src.domain.clientes.value_objects import EstadoKYC
from src.infrastructure.persistence.models import ClienteModel
from src.main import app
from src.presentation.dependencies import get_db, get_kyc_verifier


class FakeKyc(KycVerifier):
    def __init__(self, resultado: EstadoKYC):
        self.resultado = resultado

    async def verificar(
        self, tipo_documento: str, numero_identificacion: str
    ) -> EstadoKYC:
        return self.resultado


@pytest.fixture
def fake_kyc() -> FakeKyc:
    return FakeKyc(EstadoKYC.VALIDADO)


@pytest.fixture
async def kyc_app(fake_kyc: FakeKyc):
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
    app.dependency_overrides[get_kyc_verifier] = lambda: fake_kyc

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, factory

    app.dependency_overrides.clear()
    await engine.dispose()


async def _insertar_cliente(
    factory: async_sessionmaker[AsyncSession],
) -> uuid.UUID:
    async with factory() as session:
        modelo = ClienteModel(
            nombres="Ana",
            apellidos="Pérez",
            tipo_documento="CC",
            numero_identificacion="1020304050",
            correo="ana.perez@example.com",
            fecha_nacimiento="1990-05-15",
            pais_residencia="Colombia",
            telefono="+573001234567",
            estado_kyc=EstadoKYC.PENDIENTE,
        )
        session.add(modelo)
        await session.commit()
        await session.refresh(modelo)
        return modelo.id


async def test_verificar_kyc_actualiza_estado(kyc_app):
    client, factory = kyc_app
    cliente_id = await _insertar_cliente(factory)

    response = await client.post(
        f"/api/v1/identity-service/clientes/{cliente_id}/verificar-kyc"
    )

    assert response.status_code == 200
    assert response.json()["estado_kyc"] == "VALIDADO"


async def test_verificar_kyc_devuelve_404_si_cliente_no_existe(kyc_app):
    client, _ = kyc_app

    response = await client.post(
        f"/api/v1/identity-service/clientes/{uuid.uuid4()}/verificar-kyc"
    )

    assert response.status_code == 404