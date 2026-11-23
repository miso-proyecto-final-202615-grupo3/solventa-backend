import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from starlette.concurrency import run_in_threadpool

from src.application.ports.identity_provider import (
    AutenticarResult,
    IdentityProvider,
    IdentityProviderError,
    InvalidCredentialsError,
    PasswordRecoveryCodeError,
    PasswordRecoveryPasswordError,
    PasswordRecoveryRateLimitError,
)
from src.core.config import settings

logger = logging.getLogger(__name__)


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
        await self._registrar(correo, password, verificar_correo=True)

    async def registrar_prospecto(self, correo: str, password: str) -> None:
        await self._registrar(correo, password, verificar_correo=False)

    async def _registrar(self, correo: str, password: str, verificar_correo: bool) -> None:
        creado = False
        try:
            await run_in_threadpool(
                self._client.admin_create_user,
                UserPoolId=self.user_pool_id,
                Username=correo,
                UserAttributes=[
                    {"Name": "email", "Value": correo},
                    {"Name": "email_verified", "Value": str(verificar_correo).lower()},
                ],
                MessageAction="SUPPRESS",
            )
            creado = True
            await run_in_threadpool(
                self._client.admin_set_user_password,
                UserPoolId=self.user_pool_id,
                Username=correo,
                Password=password,
                Permanent=True,
            )
        except (ClientError, BotoCoreError) as exc:
            logger.exception("No se pudo registrar el usuario en Cognito.")
            if creado:
                await self.eliminar_usuario(correo)
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
                logger.exception("Credenciales inválidas al autenticar en Cognito.")
                raise InvalidCredentialsError(
                    "Credenciales inválidas."
                ) from exc
            logger.exception("No se pudo autenticar el usuario en Cognito.")
            raise IdentityProviderError(str(exc)) from exc
        except BotoCoreError as exc:
            logger.exception("Error de AWS al autenticar el usuario en Cognito.")
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
                logger.exception(
                    "No se pudo completar el cambio de contraseña en Cognito."
                )
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

    async def renovar_sesion(self, refresh_token: str) -> AutenticarResult:
        try:
            response = await run_in_threadpool(
                self._client.admin_initiate_auth,
                UserPoolId=self.user_pool_id,
                ClientId=self.client_id,
                AuthFlow="REFRESH_TOKEN_AUTH",
                AuthParameters={"REFRESH_TOKEN": refresh_token},
            )
        except ClientError as exc:
            codigo = exc.response.get("Error", {}).get("Code", "")
            if codigo in ("NotAuthorizedException", "InvalidParameterException"):
                raise InvalidCredentialsError("La sesión ya no es válida.") from exc
            logger.exception("No se pudo renovar la sesión en Cognito.")
            raise IdentityProviderError(str(exc)) from exc
        except BotoCoreError as exc:
            logger.exception("Error de AWS al renovar la sesión en Cognito.")
            raise IdentityProviderError(str(exc)) from exc

        auth_result = response.get("AuthenticationResult")
        if not auth_result:
            raise IdentityProviderError("No se obtuvo un resultado de renovación válido.")
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
            logger.exception("No se pudo eliminar el usuario de Cognito.")
            pass

    async def solicitar_recuperacion_clave(self, correo: str) -> None:
        try:
            await run_in_threadpool(
                self._client.forgot_password,
                ClientId=self.client_id,
                Username=correo,
            )
        except ClientError as exc:
            codigo = exc.response.get("Error", {}).get("Code", "")
            if codigo in (
                "UserNotFoundException",
                "InvalidParameterException",
                "CodeDeliveryFailureException",
            ):
                return
            if codigo in ("LimitExceededException", "TooManyRequestsException"):
                raise PasswordRecoveryRateLimitError(
                    "Demasiados intentos de recuperación. Intenta más tarde."
                ) from exc
            logger.warning("Cognito rechazó recuperación de clave (%s).", codigo)
            raise IdentityProviderError(
                "No se pudo procesar la recuperación de contraseña."
            ) from exc
        except BotoCoreError as exc:
            logger.warning("Error de AWS al solicitar recuperación de clave.")
            raise IdentityProviderError(
                "No se pudo procesar la recuperación de contraseña."
            ) from exc

    async def confirmar_recuperacion_clave(
        self, correo: str, codigo: str, nueva_clave: str
    ) -> None:
        try:
            await run_in_threadpool(
                self._client.confirm_forgot_password,
                ClientId=self.client_id,
                Username=correo,
                ConfirmationCode=codigo,
                Password=nueva_clave,
            )
        except ClientError as exc:
            codigo_error = exc.response.get("Error", {}).get("Code", "")
            if codigo_error in (
                "CodeMismatchException",
                "ExpiredCodeException",
                "UserNotFoundException",
                "NotAuthorizedException",
            ):
                raise PasswordRecoveryCodeError(
                    "El código es inválido o venció. Solicita uno nuevo."
                ) from exc
            if codigo_error == "InvalidPasswordException":
                raise PasswordRecoveryPasswordError(
                    "La contraseña no cumple la política de Cognito."
                ) from exc
            if codigo_error in ("LimitExceededException", "TooManyRequestsException"):
                raise PasswordRecoveryRateLimitError(
                    "Demasiados intentos. Intenta más tarde."
                ) from exc
            logger.warning("Cognito rechazó confirmación de recuperación (%s).", codigo_error)
            raise IdentityProviderError(
                "No se pudo actualizar la contraseña."
            ) from exc
        except BotoCoreError as exc:
            logger.warning("Error de AWS al confirmar recuperación de clave.")
            raise IdentityProviderError(
                "No se pudo actualizar la contraseña."
            ) from exc
