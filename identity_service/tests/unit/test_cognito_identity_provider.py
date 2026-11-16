import pytest
from botocore.exceptions import ClientError

import src.infrastructure.gateways.cognito_identity_provider as mod
from src.application.ports.identity_provider import (
    IdentityProviderError,
    InvalidCredentialsError,
    PasswordRecoveryCodeError,
    PasswordRecoveryPasswordError,
    PasswordRecoveryRateLimitError,
)
from src.infrastructure.gateways.cognito_identity_provider import CognitoIdentityProvider

AUTH_RESULT = {
    "AccessToken": "access-123",
    "IdToken": "id-123",
    "RefreshToken": "refresh-123",
    "ExpiresIn": 3600,
    "TokenType": "Bearer",
}


class FakeCognitoClient:
    def __init__(self):
        self.created: list[dict] = []
        self.passwords: list[dict] = []
        self.deleted: list[dict] = []
        self.auth_calls: list[dict] = []
        self.challenge_calls: list[dict] = []
        self.forgot_password_calls: list[dict] = []
        self.confirm_forgot_password_calls: list[dict] = []
        self.fail_crear: bool = False
        self.fail_autenticar: bool = False
        self.fail_forgot_password: str | None = None
        self.fail_confirm_forgot_password: str | None = None
        self.devolver_challenge: bool = False

    def admin_create_user(self, **kwargs):
        if self.fail_crear:
            raise ClientError(
                {
                    "Error": {
                        "Code": "UsernameExistsException",
                        "Message": "el usuario ya existe",
                    },
                    "ResponseMetadata": {},
                },
                "AdminCreateUser",
            )
        self.created.append(kwargs)
        return {"User": {"Username": kwargs["Username"]}}

    def admin_set_user_password(self, **kwargs):
        self.passwords.append(kwargs)

    def admin_delete_user(self, **kwargs):
        self.deleted.append(kwargs)

    def admin_initiate_auth(self, **kwargs):
        self.auth_calls.append(kwargs)
        if self.fail_autenticar:
            raise ClientError(
                {
                    "Error": {
                        "Code": "NotAuthorizedException",
                        "Message": "incorrect username or password",
                    },
                    "ResponseMetadata": {},
                },
                "AdminInitiateAuth",
            )
        if self.devolver_challenge:
            return {"ChallengeName": "NEW_PASSWORD_REQUIRED", "Session": "ses-1"}
        return {"AuthenticationResult": AUTH_RESULT}

    def admin_respond_to_auth_challenge(self, **kwargs):
        self.challenge_calls.append(kwargs)
        return {"AuthenticationResult": AUTH_RESULT}

    def forgot_password(self, **kwargs):
        self.forgot_password_calls.append(kwargs)
        if self.fail_forgot_password:
            raise ClientError(
                {"Error": {"Code": self.fail_forgot_password, "Message": "test"}},
                "ForgotPassword",
            )
        return {"CodeDeliveryDetails": {"DeliveryMedium": "EMAIL"}}

    def confirm_forgot_password(self, **kwargs):
        self.confirm_forgot_password_calls.append(kwargs)
        if self.fail_confirm_forgot_password:
            raise ClientError(
                {
                    "Error": {
                        "Code": self.fail_confirm_forgot_password,
                        "Message": "test",
                    }
                },
                "ConfirmForgotPassword",
            )
        return {}


@pytest.fixture
def provider(monkeypatch):
    async def fake_run_in_threadpool(func, *args, **kwargs):
        return func(*args, **kwargs)

    client = FakeCognitoClient()
    monkeypatch.setattr(mod, "run_in_threadpool", fake_run_in_threadpool)
    monkeypatch.setattr(mod.boto3, "client", lambda service, region_name: client)

    identity = CognitoIdentityProvider(
        user_pool_id="pool-1",
        client_id="client-1",
        region_name="us-east-1",
    )
    return identity, client


async def test_registra_usuario_crea_credencial(provider):
    identity, client = provider

    await identity.registrar_usuario("ana@example.com", "Secreta123")

    assert client.created[0]["UserPoolId"] == "pool-1"
    assert client.created[0]["Username"] == "ana@example.com"
    assert client.passwords[0]["Username"] == "ana@example.com"
    assert client.passwords[0]["Password"] == "Secreta123"
    assert client.passwords[0]["Permanent"] is True


async def test_registra_usuario_envuelve_error_de_cognito(provider, caplog):
    identity, client = provider
    client.fail_crear = True

    with pytest.raises(IdentityProviderError):
        await identity.registrar_usuario("ana@example.com", "Secreta123")

    assert "No se pudo registrar el usuario en Cognito." in caplog.text


async def test_elimina_usuario_de_cognito(provider):
    identity, client = provider

    await identity.eliminar_usuario("ana@example.com")

    assert client.deleted[0]["Username"] == "ana@example.com"


async def test_autentica_devuelve_tokens(provider):
    identity, client = provider

    resultado = await identity.autenticar_usuario(
        "ana@example.com", "Secreta123"
    )

    assert resultado.access_token == "access-123"
    assert resultado.id_token == "id-123"
    assert resultado.token_type == "Bearer"
    assert client.auth_calls[0]["AuthFlow"] == "ADMIN_USER_PASSWORD_AUTH"
    assert client.auth_calls[0]["AuthParameters"]["USERNAME"] == "ana@example.com"


async def test_autentica_envuelve_credenciales_invalidas(provider):
    identity, client = provider
    client.fail_autenticar = True

    with pytest.raises(InvalidCredentialsError):
        await identity.autenticar_usuario("ana@example.com", "incorrecta")


async def test_autentica_responde_cambio_de_password_obligatorio(provider):
    identity, client = provider
    client.devolver_challenge = True

    resultado = await identity.autenticar_usuario(
        "ana@example.com", "Secreta123"
    )

    assert resultado.access_token == "access-123"
    assert client.challenge_calls[0]["ChallengeName"] == "NEW_PASSWORD_REQUIRED"


async def test_renueva_sesion_con_refresh_token(provider):
    identity, client = provider

    resultado = await identity.renovar_sesion("refresh-123")

    assert resultado.access_token == "access-123"
    assert client.auth_calls[0]["AuthFlow"] == "REFRESH_TOKEN_AUTH"
    assert client.auth_calls[0]["AuthParameters"] == {"REFRESH_TOKEN": "refresh-123"}


async def test_solicita_codigo_de_recuperacion_sin_exponer_el_destino(provider):
    identity, client = provider

    await identity.solicitar_recuperacion_clave("ana@example.com")

    assert client.forgot_password_calls[0] == {
        "ClientId": "client-1",
        "Username": "ana@example.com",
    }


async def test_no_revela_si_usuario_no_existe_al_solicitar_codigo(provider):
    identity, client = provider
    client.fail_forgot_password = "UserNotFoundException"

    await identity.solicitar_recuperacion_clave("nadie@example.com")


async def test_no_falla_si_el_correo_no_tiene_destino_verificado(provider):
    identity, client = provider
    client.fail_forgot_password = "InvalidParameterException"

    await identity.solicitar_recuperacion_clave("ana@example.com")


async def test_confirma_codigo_y_nueva_clave(provider):
    identity, client = provider

    await identity.confirmar_recuperacion_clave(
        "ana@example.com", "123456", "NuevaClave123"
    )

    assert client.confirm_forgot_password_calls[0] == {
        "ClientId": "client-1",
        "Username": "ana@example.com",
        "ConfirmationCode": "123456",
        "Password": "NuevaClave123",
    }


async def test_rechaza_codigo_invalido_o_vencido(provider):
    identity, client = provider
    client.fail_confirm_forgot_password = "CodeMismatchException"

    with pytest.raises(PasswordRecoveryCodeError):
        await identity.confirmar_recuperacion_clave(
            "ana@example.com", "000000", "NuevaClave123"
        )


async def test_rechaza_clave_que_no_cumple_la_politica_de_cognito(provider):
    identity, client = provider
    client.fail_confirm_forgot_password = "InvalidPasswordException"

    with pytest.raises(PasswordRecoveryPasswordError):
        await identity.confirmar_recuperacion_clave(
            "ana@example.com", "123456", "corta"
        )


async def test_limita_intentos_de_recuperacion(provider):
    identity, client = provider
    client.fail_forgot_password = "LimitExceededException"

    with pytest.raises(PasswordRecoveryRateLimitError):
        await identity.solicitar_recuperacion_clave("ana@example.com")
