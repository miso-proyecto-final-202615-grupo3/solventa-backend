from datetime import date, timedelta

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


def _hace_anios(anios: int, dias: int = 0) -> str:
    hoy = date.today()
    return (date(hoy.year - anios, hoy.month, 1) + timedelta(days=hoy.day - 1 + dias)).isoformat()


def test_cliente_create_acepta_a_quien_cumple_18_hoy():
    payload = {**VALID_PAYLOAD, "fecha_nacimiento": _hace_anios(18)}

    assert ClienteCreate(**payload).fecha_nacimiento.isoformat() == _hace_anios(18)


@pytest.mark.parametrize("fecha", [_hace_anios(18, 1), _hace_anios(10)])
def test_cliente_create_rechaza_menores_de_edad(fecha):
    payload = {**VALID_PAYLOAD, "fecha_nacimiento": fecha}

    with pytest.raises(ValidationError, match="mayor de 18"):
        ClienteCreate(**payload)


@pytest.mark.parametrize("cedula", ["1234", "12345678901", "12a45", "123 45"])
def test_cliente_create_rechaza_cedula_no_numerica_o_fuera_de_rango(cedula):
    payload = {**VALID_PAYLOAD, "numero_identificacion": cedula}

    with pytest.raises(ValidationError):
        ClienteCreate(**payload)
