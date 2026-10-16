import json

import httpx
import pytest

from src.infrastructure.gateways.identity_service_gateway import (
    IdentityGatewayError,
    IdentityServiceGateway,
)

BASE = "http://identity-host:8000"
PATH_REGISTRO = "/api/v1/identity-service/clientes/registro"
PATH_AUTENTICAR = "/api/v1/identity-service/clientes/autenticar"
CLIENTE_ID = "95b19edf-6c4b-4437-99db-d84d0ef482fc"
PATH_CONSENTIMIENTO = (
    f"/api/v1/identity-service/clientes/{CLIENTE_ID}/consentimiento"
)
PATH_PERFIL = f"/api/v1/identity-service/clientes/{CLIENTE_ID}/perfil"

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
PAYLOAD_BODY = json.dumps(PAYLOAD).encode()


async def test_registrar_cliente_reenvia_hacia_identity_service():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            201,
            json={**PAYLOAD, "id": "uuid", "estado_kyc": "PENDIENTE"},
        )

    gateway = IdentityServiceGateway(
        base_url=BASE, transport=httpx.MockTransport(handler)
    )
    try:
        resultado = await gateway.registrar_cliente(PAYLOAD_BODY)

        assert resultado["correo"] == PAYLOAD["correo"]
        assert str(calls[0].url) == f"{BASE}{PATH_REGISTRO}"
        assert calls[0].content == PAYLOAD_BODY
        assert calls[0].headers["content-type"] == "application/json"
    finally:
        await gateway.aclose()


async def test_registrar_cliente_propaga_error_409():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409, json={"detail": "Ya existe un cliente con ese correo."}
        )

    gateway = IdentityServiceGateway(
        base_url=BASE, transport=httpx.MockTransport(handler)
    )
    try:
        with pytest.raises(IdentityGatewayError) as exc:
            await gateway.registrar_cliente(PAYLOAD_BODY)
        assert exc.value.status_code == 409
        assert "Ya existe" in exc.value.detail
    finally:
        await gateway.aclose()


async def test_registrar_cliente_mapea_error_de_red_como_503():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin conexión")

    gateway = IdentityServiceGateway(
        base_url=BASE, transport=httpx.MockTransport(handler)
    )
    try:
        with pytest.raises(IdentityGatewayError) as exc:
            await gateway.registrar_cliente(PAYLOAD_BODY)
        assert exc.value.status_code == 503
    finally:
        await gateway.aclose()


async def test_autenticar_cliente_devuelve_tokens():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": "access-123",
                "id_token": "id-123",
                "refresh_token": "refresh-123",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )

    gateway = IdentityServiceGateway(
        base_url=BASE, transport=httpx.MockTransport(handler)
    )
    try:
        resultado = await gateway.autenticar_cliente(
            json.dumps(
                {"correo": "ana.perez@example.com", "password": "Secreta123"}
            ).encode()
        )

        assert resultado["access_token"] == "access-123"
    finally:
        await gateway.aclose()


async def test_actualizar_consentimiento_reenvia_put_y_payload():
    calls: list[httpx.Request] = []
    payload = json.dumps({"estado": "REVOCADO"}).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"estado": "REVOCADO"})

    gateway = IdentityServiceGateway(
        base_url=BASE, transport=httpx.MockTransport(handler)
    )
    try:
        response = await gateway.actualizar_consentimiento(CLIENTE_ID, payload)

        assert response["estado"] == "REVOCADO"
        assert calls[0].method == "PUT"
        assert str(calls[0].url) == f"{BASE}{PATH_CONSENTIMIENTO}"
        assert calls[0].content == payload
    finally:
        await gateway.aclose()


async def test_obtener_perfil_cliente_reenvia_get():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"correo": "ana.perez@example.com"})

    gateway = IdentityServiceGateway(
        base_url=BASE, transport=httpx.MockTransport(handler)
    )
    try:
        response = await gateway.obtener_perfil_cliente(CLIENTE_ID)

        assert response["correo"] == "ana.perez@example.com"
        assert calls[0].method == "GET"
        assert str(calls[0].url) == f"{BASE}{PATH_PERFIL}"
    finally:
        await gateway.aclose()


async def test_obtener_perfil_cliente_propaga_403():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"detail": "Consentimiento revocado."})

    gateway = IdentityServiceGateway(
        base_url=BASE, transport=httpx.MockTransport(handler)
    )
    try:
        with pytest.raises(IdentityGatewayError) as exc:
            await gateway.obtener_perfil_cliente(CLIENTE_ID)
        assert exc.value.status_code == 403
        assert exc.value.detail == "Consentimiento revocado."
    finally:
        await gateway.aclose()


async def test_registrar_cliente_propaga_error_sin_cuerpo_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    gateway = IdentityServiceGateway(
        base_url=BASE, transport=httpx.MockTransport(handler)
    )
    try:
        with pytest.raises(IdentityGatewayError) as exc:
            await gateway.registrar_cliente(PAYLOAD_BODY)
        assert exc.value.status_code == 500
        assert "error" in exc.value.detail
    finally:
        await gateway.aclose()