import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from src.core.config import settings
from src.presentation import jwt_validator
from src.presentation.jwt_validator import (
    CognitoJwtValidator,
    CognitoUserInfo,
    IdentityLookupUnavailableError,
    InvalidJwtError,
)

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


class FakeLookup:
    """Sustituye a GetUser de Cognito y cuenta las llamadas."""

    def __init__(self, correo="ana@example.com"):
        self.correo = correo
        self.llamadas = 0

    def __call__(self, token):
        self.llamadas += 1
        return self.correo


@pytest.fixture
def lookup():
    return FakeLookup()


@pytest.fixture
def validator(monkeypatch, lookup):
    monkeypatch.setattr(settings, "COGNITO_REGION", REGION)
    monkeypatch.setattr(settings, "COGNITO_USER_POOL_ID", POOL)
    monkeypatch.setattr(settings, "COGNITO_CLIENT_ID", CLIENT_ID)
    instance = CognitoJwtValidator(user_lookup=lookup)
    instance._jwks = FakeJwks()
    return instance


def _token(key=_PRIVATE_KEY, **overrides):
    # Igual que Cognito con correo como alias: username es un UUID y no hay claim email.
    claims = {
        "iss": ISSUER, "sub": "sub-1", "token_use": "access", "client_id": CLIENT_ID,
        "username": "c468d418-d0b1-7086-5fe8-069bbd70a523", "exp": int(time.time()) + 300,
    }
    claims.update(overrides)
    return jwt.encode(claims, key, algorithm="RS256")


def test_token_valido_entrega_el_correo_de_cognito(validator):
    cliente = validator.validar(_token())

    assert cliente.correo == "ana@example.com"
    assert cliente.subject == "sub-1"


def test_el_correo_queda_en_cache_por_subject(validator, lookup):
    validator.validar(_token())
    validator.validar(_token())

    assert lookup.llamadas == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": int(time.time()) - 10},
        {"iss": "https://otro-emisor"},
        {"token_use": "id"},
        {"client_id": "otro-cliente"},
        {"sub": None},
    ],
)
def test_rechaza_tokens_invalidos(validator, lookup, overrides):
    with pytest.raises(InvalidJwtError):
        validator.validar(_token(**overrides))
    assert lookup.llamadas == 0


@pytest.mark.parametrize("correo", [None, "no-es-un-correo"])
def test_rechaza_usuario_sin_correo_valido(validator, lookup, correo):
    lookup.correo = correo

    with pytest.raises(InvalidJwtError):
        validator.validar(_token())


def test_rechaza_firma_de_otra_llave(validator):
    with pytest.raises(InvalidJwtError):
        validator.validar(_token(key=_OTHER_KEY))


def test_sin_configuracion_de_cognito_falla(monkeypatch):
    monkeypatch.setattr(settings, "COGNITO_USER_POOL_ID", "")

    with pytest.raises(InvalidJwtError):
        CognitoJwtValidator()


def _responder(monkeypatch, handler):
    def fake_post(url, headers=None, json=None, timeout=None):
        return handler(httpx.Request("POST", url, headers=headers, json=json))

    monkeypatch.setattr(jwt_validator.httpx, "post", fake_post)


def test_user_info_lee_el_atributo_email(monkeypatch):
    def handler(request):
        assert request.headers["X-Amz-Target"] == "AWSCognitoIdentityProviderService.GetUser"
        return httpx.Response(200, json={"Username": "uuid", "UserAttributes": [
            {"Name": "sub", "Value": "uuid"}, {"Name": "email", "Value": "ana@example.com"}]})

    _responder(monkeypatch, handler)

    assert CognitoUserInfo(REGION, 1).correo("token") == "ana@example.com"


def test_user_info_token_revocado_es_invalido(monkeypatch):
    _responder(monkeypatch, lambda request: httpx.Response(400, json={"__type": "NotAuthorizedException"}))

    with pytest.raises(InvalidJwtError):
        CognitoUserInfo(REGION, 1).correo("token")


@pytest.mark.parametrize("falla", ["red", 500])
def test_user_info_caida_de_cognito_no_es_culpa_del_cliente(monkeypatch, falla):
    def handler(request):
        if falla == "red":
            raise httpx.ConnectError("sin red", request=request)
        return httpx.Response(falla)

    _responder(monkeypatch, handler)

    with pytest.raises(IdentityLookupUnavailableError):
        CognitoUserInfo(REGION, 1).correo("token")
