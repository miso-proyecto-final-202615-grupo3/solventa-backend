import boto3
from botocore.exceptions import BotoCoreError, ClientError
from starlette.concurrency import run_in_threadpool

from src.application.ports.identity_provider import IdentityProvider
from src.application.use_cases.registrar_cliente_use_case import IdentityProviderError
from src.core.config import settings


class CognitoIdentityProvider(IdentityProvider):
    """Crea/elimina credenciales en Cognito.

    En EKS autentica de forma automática por Pod Identity (cadena de
    credenciales por defecto de boto3); en local usa las credenciales del
    entorno/perfil de AWS.
    """

    def __init__(
        self,
        user_pool_id: str | None = None,
        region_name: str | None = None,
    ) -> None:
        self.user_pool_id = user_pool_id or settings.COGNITO_USER_POOL_ID
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

    async def eliminar_usuario(self, correo: str) -> None:
        try:
            await run_in_threadpool(
                self._client.admin_delete_user,
                UserPoolId=self.user_pool_id,
                Username=correo,
            )
        except (ClientError, BotoCoreError):
            pass