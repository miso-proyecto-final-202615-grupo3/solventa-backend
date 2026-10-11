import httpx
import respx
from httpx import AsyncClient

from src.core.config import settings

PATH_REGISTRO = (
    f"{settings.IDENTITY_SERVICE_URL}/api/v1/identity-service/clientes/registro"
)
PATH_AUTENTICAR = (
    f"{settings.IDENTITY_SERVICE_URL}/api/v1/identity-service/clientes/autenticar"
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


async def test_registro_en_el_bff_devuelve_201(async_client: AsyncClient):
    respx.post(PATH_REGISTRO).mock(
        return_value=httpx.Response(
            201, json={**PAYLOAD, "id": "uuid", "estado_kyc": "PENDIENTE"}
        )
    )

    response = await async_client.post(
        "/api/v1/bff-web/clientes/registro", json=PAYLOAD
    )

    assert response.status_code == 201
    assert response.json()["correo"] == PAYLOAD["correo"]


async def test_registro_en_el_bff_propaga_409(async_client: AsyncClient):
    respx.post(PATH_REGISTRO).mock(
        return_value=httpx.Response(
            409, json={"detail": "Ya existe un cliente con ese correo."}
        )
    )

    response = await async_client.post(
        "/api/v1/bff-web/clientes/registro", json=PAYLOAD
    )

    assert response.status_code == 409
    assert "Ya existe" in response.json()["detail"]


async def test_registro_en_el_bff_devuelve_422_con_payload_invalido(
    async_client: AsyncClient,
):
    invalid = {**PAYLOAD, "correo": "no-es-correo"}

    response = await async_client.post(
        "/api/v1/bff-web/clientes/registro", json=invalid
    )

    assert response.status_code == 422


async def test_autenticar_en_el_bff_devuelve_tokens(async_client: AsyncClient):
    respx.post(PATH_AUTENTICAR).mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "access-123",
                "id_token": "id-123",
                "refresh_token": "refresh-123",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )
    )

    response = await async_client.post(
        "/api/v1/bff-web/clientes/autenticar",
        json={"correo": "ana.perez@example.com", "password": "Secreta123"},
    )

    assert response.status_code == 200
    assert response.json()["access_token"] == "access-123"