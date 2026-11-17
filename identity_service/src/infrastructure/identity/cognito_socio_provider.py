import boto3
from starlette.concurrency import run_in_threadpool

from src.core.config import settings


class CognitoSocioProvider:
    def __init__(self) -> None:
        self._client = boto3.client("cognito-idp", region_name=settings.AWS_REGION)

    async def invitar(self, correo: str) -> None:
        await run_in_threadpool(
            self._client.admin_create_user,
            UserPoolId=settings.COGNITO_USER_POOL_ID,
            Username=correo,
            UserAttributes=[
                {"Name": "email", "Value": correo},
                {"Name": "email_verified", "Value": "true"},
            ],
        )
        await run_in_threadpool(
            self._client.admin_add_user_to_group,
            UserPoolId=settings.COGNITO_USER_POOL_ID,
            Username=correo,
            GroupName=settings.COGNITO_SOCIO_GROUP,
        )
