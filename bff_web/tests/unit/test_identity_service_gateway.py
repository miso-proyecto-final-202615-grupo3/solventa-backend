import httpx
import pytest
import respx

from src.infrastructure.gateways.identity_service_gateway import (
    IdentityGatewayError,
    IdentityServiceGateway,
)

BASE = "http://identity-host:8000"
PATH_REGISTRO = "/api/v1/identity-service/clientes/registro"
PATH_AUTENTICAR = "/api/v1/identity-service/clientes/autenticar"

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


async def test_registrar_cliente_reenvia_hacia_identity_service():
    route = respx.post(f"{BASE}{PATH_REGISTRO}").mock(
        return_value=httpx.Response(201, json={**PAYLOAD, "id": "uuid", "estado_kyc": "PENDIENTE"})
    )
    gateway = IdentityServiceGateway(base_url=BASE)
    try:
        resultado = await gateway.registrar_cliente(PAYLOAD)

        assert resultado["correo"] == PAYLOAD["correo"]
        assert route.called
        assert route.calls[0].request.json() == PAYLOAD
    finally:
        await gateway.aclose()


async def test_registrar_cliente_propaga_error_409():
    respx.post(f"{BASE}{PATH_REGISTRO}").mock(
        return_value=httpx.Response(
            409, json={"detail": "Ya existe un cliente con ese correo."}
        )
    )
    gateway = IdentityServiceGateway(base_url=BASE)
    try:
        with pytest.raises(IdentityGatewayError) as exc:
            await gateway.registrar_cliente(PAYLOAD)
        assert exc.value.status_code == 409
    finally:
        await gateway.aclose()


async def test_autenticar_cliente_devuelve_tokens():
    respx.post(f"{BASE}{PATH_AUTENTICAR}").mock(
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
    gateway = IdentityServiceGateway(base_url=BASE)
    try:
        resultado = await gateway.autenticar_cliente(
            {"correo": "ana.perez@example.com", "password": "Secreta123"}
        )

        assert resultado["access_token"] == "access-123"
    finally:
        await gateway.aclose()