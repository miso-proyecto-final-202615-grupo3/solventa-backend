import uuid
from datetime import date

from src.infrastructure.persistence.models import ClienteModel, DispositivoVinculadoModel
from src.main import app
from src.presentation.dependencies import get_db


async def test_resumen_indica_si_la_instalacion_esta_vinculada(async_client, db_session):
    cliente = ClienteModel(
        nombres="Ana", apellidos="Pérez", tipo_documento="CC",
        numero_identificacion="1020304050", correo="ana@example.com",
        fecha_nacimiento=date(1990, 1, 1), pais_residencia="Colombia",
        telefono="+573001234567",
    )
    db_session.add(cliente)
    await db_session.flush()
    installation_id = uuid.uuid4()
    db_session.add(DispositivoVinculadoModel(
        cliente_id=cliente.id, installation_id=installation_id, plataforma="ANDROID",
        modelo="Pixel", version_so="14", folio_verificacion="folio-1",
    ))
    await db_session.commit()

    async def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    try:
        response = await async_client.get(
            "/api/v1/identity-service/clientes/resumen-movil",
            params={"correo": cliente.correo, "installation_id": str(installation_id)},
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json()["dispositivo_vinculado"] is True
