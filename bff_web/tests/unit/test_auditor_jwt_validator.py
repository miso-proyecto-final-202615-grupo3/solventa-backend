import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from src.core.config import settings
from src.presentation import auditor_jwt_validator
from src.presentation.auditor_jwt_validator import (
    AuditorTokenConfiguracionError,
    AuditorTokenError,
    CognitoAuditorJwtValidator,
)

REGION = "us-east-1"
POOL = "us-east-1_AUDIT"
CLIENT = "solventa-web"
ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{POOL}"
PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class SigningKey:
    def __init__(self, key):
        self.key = key


class FakeJwks:
    def get_signing_key_from_jwt(self, token):
        return SigningKey(PRIVATE_KEY.public_key())


@pytest.fixture
def validator(monkeypatch):
    monkeypatch.setattr(settings, "COGNITO_REGION", REGION)
    monkeypatch.setattr(settings, "COGNITO_USER_POOL_ID", POOL)
    monkeypatch.setattr(settings, "COGNITO_CLIENT_ID", CLIENT)
    monkeypatch.setattr(settings, "COGNITO_AUDITOR_GROUP", "Auditor")
    monkeypatch.setattr(auditor_jwt_validator, "PyJWKClient", lambda *args, **kwargs: FakeJwks())
    return CognitoAuditorJwtValidator()


def token(key=PRIVATE_KEY, **claims):
    data = {
        "iss": ISSUER,
        "sub": "auditor-1",
        "token_use": "access",
        "client_id": CLIENT,
        "cognito:groups": ["Auditor"],
        "exp": int(time.time()) + 300,
    }
    data.update(claims)
    return jwt.encode(data, key, algorithm="RS256")


def test_valida_firma_emisor_cliente_y_grupo_auditor(validator):
    assert validator.validar(token()) == "auditor-1"


@pytest.mark.parametrize(
    "claims",
    [
        {"exp": int(time.time()) - 1},
        {"iss": "https://otro-pool"},
        {"token_use": "id"},
        {"client_id": "otro-cliente"},
        {"cognito:groups": ["Cliente"]},
        {"sub": ""},
    ],
)
def test_rechaza_token_invalido_o_no_autorizado(validator, claims):
    with pytest.raises((AuditorTokenError, PermissionError)):
        validator.validar(token(**claims))


def test_rechaza_firma_de_otra_llave(validator):
    with pytest.raises(AuditorTokenError):
        validator.validar(token(key=OTHER_KEY))


def test_rechaza_token_sin_vencimiento(validator):
    claims = jwt.decode(token(), options={"verify_signature": False})
    del claims["exp"]
    with pytest.raises(AuditorTokenError):
        validator.validar(jwt.encode(claims, PRIVATE_KEY, algorithm="RS256"))


def test_falla_cerrado_si_falta_configuracion(monkeypatch):
    monkeypatch.setattr(settings, "COGNITO_USER_POOL_ID", "")
    with pytest.raises(AuditorTokenConfiguracionError):
        CognitoAuditorJwtValidator()
