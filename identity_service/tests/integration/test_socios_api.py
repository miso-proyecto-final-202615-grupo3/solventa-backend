import pytest

from src.main import app
from src.presentation.dependencies import get_db


@pytest.fixture
async def socios_client(async_client, db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield async_client
    finally:
        app.dependency_overrides.pop(get_db, None)


async def test_registra_socio_y_audita_actor(socios_client):
    response = await socios_client.post(
        "/api/v1/identity-service/socios",
        headers={"X-Actor-Id": "operator-123"},
        json={
            "nombre": " Banco Andino ",
            "correo": "socio@yopmail.com",
            "tipo_socio": " Banco ",
            "canal_integracion": " API ",
        },
    )

    assert response.status_code == 201
    assert response.json()["nombre"] == "Banco Andino"
    assert response.json()["estado"] == "ACTIVO"


async def test_rechaza_correo_duplicado(socios_client):
    payload = {
        "nombre": "Banco Andino",
        "correo": "socio@yopmail.com",
        "tipo_socio": "Banco",
        "canal_integracion": "API",
    }
    headers = {"X-Actor-Id": "operator-123"}

    assert (
        await socios_client.post(
            "/api/v1/identity-service/socios", headers=headers, json=payload
        )
    ).status_code == 201
    response = await socios_client.post(
        "/api/v1/identity-service/socios", headers=headers, json=payload
    )

    assert response.status_code == 409
