import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from src.core.config import settings
from src.presentation.jwt_validator import CognitoJwtValidator, InvalidJwtError

REGION = "us-east-1"
POOL = "us-east-1_TEST"
CLIENT_ID = "cliente-movil"
ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{POOL}"

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _SigningKey:
    def __init__(self, key):
        self.key = key


class FakeJwks:
    """Sustituye al JWKS de Cognito: entrega siempre la llave pública de la prueba."""

    def get_signing_key_from_jwt(self, token):
        return _SigningKey(_PRIVATE_KEY.public_key())


@pytest.fixture
def validator(monkeypatch):
    monkeypatch.setattr(settings, "COGNITO_REGION", REGION)
    monkeypatch.setattr(settings, "COGNITO_USER_POOL_ID", POOL)
    monkeypatch.setattr(settings, "COGNITO_CLIENT_ID", CLIENT_ID)
    instance = CognitoJwtValidator()
    instance._jwks = FakeJwks()
    return instance


def _token(key=_PRIVATE_KEY, **overrides):
    claims = {
        "iss": ISSUER, "sub": "sub-1", "token_use": "access", "client_id": CLIENT_ID,
        "username": "ana@example.com", "exp": int(time.time()) + 300,
    }
    claims.update(overrides)
    return jwt.encode(claims, key, algorithm="RS256")


def test_token_valido_entrega_el_correo(validator):
    cliente = validator.validar(_token())

    assert cliente.correo == "ana@example.com"
    assert cliente.subject == "sub-1"


@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": int(time.time()) - 10},
        {"iss": "https://otro-emisor"},
        {"token_use": "id"},
        {"client_id": "otro-cliente"},
        {"username": "no-es-un-correo"},
    ],
)
def test_rechaza_tokens_invalidos(validator, overrides):
    with pytest.raises(InvalidJwtError):
        validator.validar(_token(**overrides))


def test_rechaza_firma_de_otra_llave(validator):
    with pytest.raises(InvalidJwtError):
        validator.validar(_token(key=_OTHER_KEY))


def test_sin_configuracion_de_cognito_falla(monkeypatch):
    monkeypatch.setattr(settings, "COGNITO_USER_POOL_ID", "")

    with pytest.raises(InvalidJwtError):
        CognitoJwtValidator()
