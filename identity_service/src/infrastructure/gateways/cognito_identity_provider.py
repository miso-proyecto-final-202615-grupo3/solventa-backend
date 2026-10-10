import boto3
from botocore.exceptions import BotoCoreError, ClientError
from starlette.concurrency import run_in_threadpool

from src.application.ports.identity_provider import (
    AutenticarResult,
    IdentityProvider,
    IdentityProviderError,
    InvalidCredentialsError,
)
from src.core.config import settings


class CognitoIdentityProvider(IdentityProvider):
    """Crea/autentica/elimina credenciales en Cognito.

    En EKS autentica de forma automática por Pod Identity (cadena de
    credenciales por defecto de boto3); en local usa las credenciales del
    entorno/perfil de AWS.
    """

    def __init__(
        self,
        user_pool_id: str | None = None,
        client_id: str | None = None,
        region_name: str | None = None,
    ) -> None:
        self.user_pool_id = user_pool_id or settings.COGNITO_USER_POOL_ID
        self.client_id = client_id or settings.COGNITO_CLIENT_ID
        self.region_name = region_name or settings.AWS_REGION
        self._client = boto3.client("cognito-idp", region_name=self.region_name)

    async def registrar_usuario(self, correo: str, password: str) -> None:
        try:
            await run_in_threadpool(
                self._client.admin_create_user,
                UserPoolId=self.user_pool_id,
                Username=correo,
                UserAttributes=[
                    {"Name": "email", "Value": correo},
                    {"Name": "email_verified", "Value": "true"},
                ],
                MessageAction="SUPPRESS",
            )
            await run_in_threadpool(
                self._client.admin_set_user_password,
                UserPoolId=self.user_pool_id,
                Username=correo,
                Password=password,
                Permanent=True,
            )
        except (ClientError, BotoCoreError) as exc:
            raise IdentityProviderError(str(exc)) from exc

    async def autenticar_usuario(
        self, correo: str, password: str
    ) -> AutenticarResult:
        try:
            response = await run_in_threadpool(
                self._client.admin_initiate_auth,
                UserPoolId=self.user_pool_id,
                ClientId=self.client_id,
                AuthFlow="ADMIN_USER_PASSWORD_AUTH",
                AuthParameters={"USERNAME": correo, "PASSWORD": password},
            )
        except ClientError as exc:
            codigo = exc.response.get("Error", {}).get("Code", "")
            if codigo in ("NotAuthorizedException", "UserNotFoundException"):
                raise InvalidCredentialsError(
                    "Credenciales inválidas."
                ) from exc
            raise IdentityProviderError(str(exc)) from exc
        except BotoCoreError as exc:
            raise IdentityProviderError(str(exc)) from exc

        if response.get("ChallengeName") == "NEW_PASSWORD_REQUIRED":
            try:
                response = await run_in_threadpool(
                    self._client.admin_respond_to_auth_challenge,
                    UserPoolId=self.user_pool_id,
                    ClientId=self.client_id,
                    ChallengeName="NEW_PASSWORD_REQUIRED",
                    ChallengeResponses={
                        "USERNAME": correo,
                        "NEW_PASSWORD": password,
                    },
                    Session=response.get("Session"),
                )
            except ClientError as exc:
                raise InvalidCredentialsError(
                    "No se pudo completar la autenticación."
                ) from exc

        auth_result = response.get("AuthenticationResult")
        if not auth_result:
            raise IdentityProviderError(
                "No se obtuvo un resultado de autenticación válido."
            )

        return AutenticarResult(
            access_token=auth_result["AccessToken"],
            id_token=auth_result.get("IdToken", ""),
            refresh_token=auth_result.get("RefreshToken"),
            expires_in=auth_result.get("ExpiresIn"),
            token_type=auth_result.get("TokenType", "Bearer"),
        )

    async def eliminar_usuario(self, correo: str) -> None:
        try:
            await run_in_threadpool(
                self._client.admin_delete_user,
                UserPoolId=self.user_pool_id,
                Username=correo,
            )
        except (ClientError, BotoCoreError):
            pass