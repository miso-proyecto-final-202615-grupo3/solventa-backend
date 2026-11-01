import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from src.infrastructure.persistence.models import ClienteModel, ConsentimientoBiometricoModel
from src.main import app
from src.presentation.dependencies import get_db

URL = "/api/v1/identity-service/clientes/consentimiento-biometrico"


@pytest.fixture
async def cliente(db_session):
    model = ClienteModel(
        nombres="Ana", apellidos="Pérez", tipo_documento="CC",
        numero_identificacion="1020304050", correo="ana@example.com",
        fecha_nacimiento=date(1990, 1, 1), pais_residencia="Colombia",
        telefono="+573001234567",
    )
    db_session.add(model)
    await db_session.commit()

    async def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    yield model
    app.dependency_overrides.pop(get_db, None)


def _payload(**cambios):
    payload = {
        "correo": "ana@example.com",
        "decision": "ACEPTADO",
        "version_terminos": "1.0",
        "installation_id": str(uuid.uuid4()),
        "decidido_en": datetime.now(UTC).isoformat(),
    }
    payload.update(cambios)
    return payload


async def test_sin_decision_el_consentimiento_no_esta_otorgado(async_client, cliente):
    response = await async_client.get(URL, params={"correo": cliente.correo})

    assert response.status_code == 200
    assert response.json() == {
        "otorgado": False, "version_vigente": "1.0", "version_aceptada": None, "decidido_en": None,
    }


async def test_aceptar_y_luego_rechazar_deja_ambas_decisiones_auditables(async_client, cliente, db_session):
    aceptado = await async_client.post(URL, json=_payload(), headers={"X-Correlation-Id": "corr-1"})
    assert aceptado.status_code == 201
    assert aceptado.json()["decision"] == "ACEPTADO"
    assert aceptado.json()["version_terminos"] == "1.0"
    assert aceptado.json()["registrado_en"]

    estado = (await async_client.get(URL, params={"correo": cliente.correo})).json()
    assert estado["otorgado"] is True
    assert estado["version_aceptada"] == "1.0"

    rechazado = await async_client.post(URL, json=_payload(decision="RECHAZADO"))
    assert rechazado.status_code == 201
    assert (await async_client.get(URL, params={"correo": cliente.correo})).json()["otorgado"] is False

    registros = (
        await db_session.execute(
            select(ConsentimientoBiometricoModel)
            .where(ConsentimientoBiometricoModel.cliente_id == cliente.id)
            .order_by(ConsentimientoBiometricoModel.registrado_en)
        )
    ).scalars().all()
    assert [r.decision for r in registros] == ["ACEPTADO", "RECHAZADO"]
    assert all(r.version_terminos == "1.0" and r.decidido_en and r.registrado_en for r in registros)


async def test_version_no_vigente_responde_409(async_client, cliente):
    response = await async_client.post(URL, json=_payload(version_terminos="0.9"))

    assert response.status_code == 409
    assert response.json()["detail"]["codigo"] == "VERSION_TERMINOS_DESACTUALIZADA"


@pytest.mark.parametrize(
    "cambios",
    [
        {"decision": "QUIZAS"},
        {"decidido_en": "2026-11-02T15:00:00"},
        {"installation_id": "no-es-uuid"},
        {"version_terminos": ""},
        {"extra": "x"},
    ],
    ids=["decision", "fecha-sin-zona", "instalacion", "version-vacia", "campo-extra"],
)
async def test_datos_invalidos_responden_422(async_client, cliente, cambios):
    response = await async_client.post(URL, json=_payload(**cambios))

    assert response.status_code == 422


async def test_fecha_en_el_futuro_responde_422(async_client, cliente):
    futura = (datetime.now(UTC) + timedelta(hours=1)).isoformat()

    response = await async_client.post(URL, json=_payload(decidido_en=futura))

    assert response.status_code == 422
    assert response.json()["detail"]["codigo"] == "DATOS_INVALIDOS"


async def test_cliente_inexistente_responde_404(async_client, cliente):
    assert (await async_client.get(URL, params={"correo": "nadie@example.com"})).status_code == 404
    assert (await async_client.post(URL, json=_payload(correo="nadie@example.com"))).status_code == 404
