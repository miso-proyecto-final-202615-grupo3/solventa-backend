from datetime import date, datetime

import pytest
from fastapi import HTTPException

from src.application.ports.identity_provider import (
    AutenticarResult,
    IdentityProviderError,
    InvalidCredentialsError,
)
from src.application.use_cases.registrar_cliente_use_case import DuplicateClienteError
from src.domain.clientes.entities import Cliente, ClienteId
from src.domain.clientes.value_objects import EstadoKYC
from src.presentation.routers.clientes import autenticar_cliente, registrar_cliente
from src.presentation.schemas import ClienteCreate, PasswordVerify

PAYLOAD = ClienteCreate(
    nombres="Ana",
    apellidos="Pérez",
    tipo_documento="CC",
    numero_identificacion="1020304050",
    correo="ana.perez@example.com",
    password="Secreta123",
    fecha_nacimiento=date(1990, 5, 15),
    pais_residencia="Colombia",
    telefono="+573001234567",
)

CREDENCIALES = PasswordVerify(
    correo="ana.perez@example.com", password="Secreta123"
)


class UseCaseOK:
    async def ejecutar(self, payload):
        return Cliente(
            id=ClienteId(),
            nombres=payload.nombres,
            apellidos=payload.apellidos,
            tipo_documento=payload.tipo_documento.value,
            numero_identificacion=payload.numero_identificacion,
            correo=str(payload.correo),
            fecha_nacimiento=payload.fecha_nacimiento,
            pais_residencia=payload.pais_residencia,
            telefono=payload.telefono,
            estado_kyc=EstadoKYC.PENDIENTE,
            fecha_creacion=datetime(2026, 10, 10),
            fecha_actualizacion=datetime(2026, 10, 10),
        )


class UseCaseDuplicado:
    async def ejecutar(self, payload):
        raise DuplicateClienteError("Ya existe un cliente con ese correo.")


class UseCaseIdentidad:
    async def ejecutar(self, payload):
        raise IdentityProviderError("cognito falló")


class AuthUseCaseOK:
    async def ejecutar(self, payload):
        return AutenticarResult(
            access_token="access-123",
            id_token="id-123",
            refresh_token="refresh-123",
            expires_in=3600,
        )


class AuthUseCaseInvalidas:
    async def ejecutar(self, payload):
        raise InvalidCredentialsError("credenciales inválidas")


class AuthUseCaseFallo:
    async def ejecutar(self, payload):
        raise IdentityProviderError("cognito inaccesible")


async def test_registrar_devuelve_respuesta():
    response = await registrar_cliente(PAYLOAD, UseCaseOK())

    assert response.correo == PAYLOAD.correo
    assert response.tipo_documento.value == "CC"
    assert response.estado_kyc == EstadoKYC.PENDIENTE
    assert response.id is not None


async def test_registrar_mapea_duplicado_como_409():
    with pytest.raises(HTTPException) as exc:
        await registrar_cliente(PAYLOAD, UseCaseDuplicado())

    assert exc.value.status_code == 409


async def test_registrar_mapea_error_de_identidad_como_503():
    with pytest.raises(HTTPException) as exc:
        await registrar_cliente(PAYLOAD, UseCaseIdentidad())

    assert exc.value.status_code == 503


async def test_autenticar_devuelve_tokens():
    response = await autenticar_cliente(CREDENCIALES, AuthUseCaseOK())

    assert response.access_token == "access-123"
    assert response.token_type == "Bearer"


async def test_autenticar_mapea_credenciales_invalidas_como_401():
    with pytest.raises(HTTPException) as exc:
        await autenticar_cliente(CREDENCIALES, AuthUseCaseInvalidas())

    assert exc.value.status_code == 401


async def test_autenticar_mapea_error_de_proveedor_como_503():
    with pytest.raises(HTTPException) as exc:
        await autenticar_cliente(CREDENCIALES, AuthUseCaseFallo())

    assert exc.value.status_code == 503