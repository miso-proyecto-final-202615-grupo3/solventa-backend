import pytest
from pydantic import ValidationError

from src.domain.clientes.value_objects import TipoDocumento
from src.presentation.schemas import ClienteCreate, ClienteResponse, PasswordVerify

VALID_PAYLOAD = {
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


def test_cliente_create_valido():
    cliente = ClienteCreate(**VALID_PAYLOAD)

    assert cliente.tipo_documento == TipoDocumento.CC
    assert cliente.correo == "ana.perez@example.com"
    assert cliente.nombres == "Ana"


def test_cliente_create_default_tipo_documento():
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "tipo_documento"}

    cliente = ClienteCreate(**payload)

    assert cliente.tipo_documento == TipoDocumento.CC


def test_cliente_create_rechaza_correo_invalido():
    payload = {**VALID_PAYLOAD, "correo": "no-es-un-correo"}

    with pytest.raises(ValidationError):
        ClienteCreate(**payload)


def test_cliente_create_rechaza_tipo_documento_no_soportado():
    payload = {**VALID_PAYLOAD, "tipo_documento": "CE"}

    with pytest.raises(ValidationError):
        ClienteCreate(**payload)


def test_cliente_create_rechaza_fecha_nacimiento_futura():
    payload = {**VALID_PAYLOAD, "fecha_nacimiento": "2999-01-01"}

    with pytest.raises(ValidationError):
        ClienteCreate(**payload)


def test_cliente_create_rechaza_telefono_invalido():
    payload = {**VALID_PAYLOAD, "telefono": "telefono"}

    with pytest.raises(ValidationError):
        ClienteCreate(**payload)


def test_cliente_create_rechaza_password_corta():
    payload = {**VALID_PAYLOAD, "password": "corta"}

    with pytest.raises(ValidationError):
        ClienteCreate(**payload)


def test_cliente_create_rechaza_campos_extra():
    payload = {**VALID_PAYLOAD, "campo_extra": "x"}

    with pytest.raises(ValidationError):
        ClienteCreate(**payload)


def test_cliente_response_no_expone_password():
    assert "password" not in ClienteResponse.model_fields


def test_password_verify_valido():
    credenciales = PasswordVerify(
        correo="ana.perez@example.com", password="Secreta123"
    )

    assert credenciales.correo == "ana.perez@example.com"


def test_password_verify_rechaza_correo_invalido():
    with pytest.raises(ValidationError):
        PasswordVerify(correo="invalido", password="Secreta123")
