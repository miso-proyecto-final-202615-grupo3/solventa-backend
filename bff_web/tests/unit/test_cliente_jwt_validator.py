import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from src.core.config import settings
from src.presentation import cliente_jwt_validator
from src.presentation.cliente_jwt_validator import ClienteTokenError, CognitoClienteJwtValidator

PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
ISSUER = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_POOL"


@pytest.fixture
def validator(monkeypatch):
    class Jwks:
        def get_signing_key_from_jwt(self, token):
            class Key:
                key = PRIVATE_KEY.public_key()
            return Key()

    monkeypatch.setattr(settings, "COGNITO_REGION", "us-east-1")
    monkeypatch.setattr(settings, "COGNITO_USER_POOL_ID", "us-east-1_POOL")
    monkeypatch.setattr(settings, "COGNITO_CLIENT_ID", "web")
    monkeypatch.setattr(cliente_jwt_validator, "PyJWKClient", lambda *args, **kwargs: Jwks())
    return CognitoClienteJwtValidator()


def token(key=PRIVATE_KEY, **claims):
    data = {"iss": ISSUER, "sub": "cliente", "token_use": "access", "client_id": "web", "exp": int(time.time()) + 300}
    data.update(claims)
    return jwt.encode(data, key, algorithm="RS256")


def test_token_valido(validator):
    assert validator.validar(token()) == "cliente"


@pytest.mark.parametrize("claims", [
    {"exp": int(time.time()) - 1}, {"iss": "https://otro"},
    {"token_use": "id"}, {"client_id": "otro"}, {"sub": ""},
])
def test_rechaza_claims_invalidos(validator, claims):
    with pytest.raises(ClienteTokenError):
        validator.validar(token(**claims))


def test_rechaza_firma_ajena(validator):
    with pytest.raises(ClienteTokenError):
        validator.validar(token(key=OTHER_KEY))
