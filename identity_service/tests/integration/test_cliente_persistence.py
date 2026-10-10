import uuid
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from src.domain.clientes.value_objects import EstadoKYC
from src.infrastructure.persistence.models import ClienteModel


def _cliente(correo: str = "ana.perez@example.com",
             numero_identificacion: str = "1020304050") -> ClienteModel:
    return ClienteModel(
        nombres="Ana",
        apellidos="Pérez",
        tipo_documento="CC",
        numero_identificacion=numero_identificacion,
        correo=correo,
        fecha_nacimiento=date(1990, 5, 15),
        pais_residencia="Colombia",
        telefono="+573001234567",
    )


async def test_crea_cliente_con_campos_completos(db_session):
    cliente = _cliente()

    db_session.add(cliente)
    await db_session.commit()
    await db_session.refresh(cliente)

    assert isinstance(cliente.id, uuid.UUID)
    assert cliente.nombres == "Ana"
    assert cliente.apellidos == "Pérez"
    assert cliente.tipo_documento == "CC"
    assert cliente.numero_identificacion == "1020304050"
    assert cliente.correo == "ana.perez@example.com"
    assert cliente.fecha_nacimiento == date(1990, 5, 15)
    assert cliente.pais_residencia == "Colombia"
    assert cliente.telefono == "+573001234567"
    assert cliente.estado_kyc == EstadoKYC.PENDIENTE
    assert cliente.fecha_creacion is not None
    assert cliente.fecha_actualizacion is not None


async def test_estado_kyc_por_defecto_pendiente(db_session):
    cliente = _cliente()

    db_session.add(cliente)
    await db_session.commit()
    await db_session.refresh(cliente)

    assert cliente.estado_kyc == EstadoKYC.PENDIENTE


async def test_genera_uuid_al_crear(db_session):
    cliente = _cliente()

    db_session.add(cliente)
    await db_session.commit()
    await db_session.refresh(cliente)

    assert cliente.id is not None


async def test_rechaza_correo_duplicado(db_session):
    db_session.add(_cliente(correo="duplicado@example.com"))
    await db_session.commit()

    db_session.add(_cliente(correo="duplicado@example.com"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_rechaza_documento_duplicado(db_session):
    db_session.add(_cliente(numero_identificacion="999999999"))
    await db_session.commit()

    db_session.add(_cliente(numero_identificacion="999999999"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_permite_mismo_numero_con_distinto_tipo_documento(db_session):
    db_session.add(
        _cliente(numero_identificacion="888888888")
    )
    await db_session.commit()

    db_session.add(
        ClienteModel(
            nombres="Luis",
            apellidos="Gómez",
            tipo_documento="CE",
            numero_identificacion="888888888",
            correo="luis.gomez@example.com",
            fecha_nacimiento=date(1988, 3, 10),
            pais_residencia="Chile",
            telefono="+56912345678",
        )
    )
    await db_session.commit()