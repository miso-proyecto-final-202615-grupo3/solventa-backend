from datetime import date, datetime

import pytest
from fastapi import HTTPException

from src.application.use_cases.registrar_cliente_use_case import (
    DuplicateClienteError,
    IdentityProviderError,
)
from src.domain.clientes.entities import Cliente, ClienteId
from src.domain.clientes.value_objects import EstadoKYC
from src.presentation.routers.clientes import registrar_cliente
from src.presentation.schemas import ClienteCreate

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