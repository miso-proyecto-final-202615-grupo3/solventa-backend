import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from src.core.config import settings
from src.presentation import socios_admin_jwt_validator
from src.presentation.socios_admin_jwt_validator import (
    CognitoSociosAdminJwtValidator,
    SociosAdminTokenConfiguracionError,
    SociosAdminTokenError,
)

REGION = "us-east-1"
POOL = "us-east-1_PARTNERS"
CLIENT = "solventa-web"
ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{POOL}"
PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


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
    monkeypatch.setattr(settings, "COGNITO_SOCIOS_ADMIN_GROUP", "SociosAdmin")
    monkeypatch.setattr(
        socios_admin_jwt_validator,
        "PyJWKClient",
        lambda *args, **kwargs: FakeJwks(),
    )
    return CognitoSociosAdminJwtValidator()


def token(**claims):
    data = {
        "iss": ISSUER,
        "sub": "operator-1",
        "token_use": "access",
        "client_id": CLIENT,
        "cognito:groups": ["SociosAdmin"],
        "exp": int(time.time()) + 300,
    }
    data.update(claims)
    return jwt.encode(data, PRIVATE_KEY, algorithm="RS256")


def test_acepta_token_de_administrador_de_socios(validator):
    assert validator.validar(token()) == "operator-1"


@pytest.mark.parametrize(
    "claims",
    [
        {"token_use": "id"},
        {"client_id": "otro-cliente"},
        {"cognito:groups": ["Cliente"]},
        {"sub": ""},
    ],
)
def test_rechaza_token_sin_permisos_para_administrar_socios(validator, claims):
    with pytest.raises((SociosAdminTokenError, PermissionError)):
        validator.validar(token(**claims))


def test_rechaza_token_sin_vencimiento(validator):
    claims = jwt.decode(token(), options={"verify_signature": False})
    del claims["exp"]
    with pytest.raises(SociosAdminTokenError):
        validator.validar(jwt.encode(claims, PRIVATE_KEY, algorithm="RS256"))


def test_falla_cerrado_si_falta_configuracion(monkeypatch):
    monkeypatch.setattr(settings, "COGNITO_USER_POOL_ID", "")
    with pytest.raises(SociosAdminTokenConfiguracionError):
        CognitoSociosAdminJwtValidator()
