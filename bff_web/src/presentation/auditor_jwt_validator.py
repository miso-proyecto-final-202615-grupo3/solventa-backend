from functools import lru_cache

import jwt
from jwt import PyJWKClient

from src.core.config import settings


class AuditorTokenError(Exception):
    pass


class AuditorTokenConfiguracionError(Exception):
    pass


class CognitoAuditorJwtValidator:
    def __init__(self) -> None:
        if not settings.COGNITO_REGION or not settings.COGNITO_USER_POOL_ID or not settings.COGNITO_CLIENT_ID:
            raise AuditorTokenConfiguracionError("Cognito no está configurado para auditoría.")
        self.issuer = (
            f"https://cognito-idp.{settings.COGNITO_REGION}.amazonaws.com/"
            f"{settings.COGNITO_USER_POOL_ID}"
        )
        self.jwks = PyJWKClient(
            f"{self.issuer}/.well-known/jwks.json",
            cache_keys=True,
            lifespan=settings.COGNITO_JWKS_TTL_SECONDS,
        )

    def validar(self, token: str) -> str:
        try:
            key = self.jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                issuer=self.issuer,
                options={"verify_aud": False, "require": ["exp", "iss", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise AuditorTokenError("Token inválido o vencido.") from exc

        if claims.get("token_use") != "access" or claims.get("client_id") != settings.COGNITO_CLIENT_ID:
            raise AuditorTokenError("Tipo de token no permitido.")
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise AuditorTokenError("El token no contiene una identidad válida.")
        grupos = claims.get("cognito:groups", [])
        if not isinstance(grupos, list) or settings.COGNITO_AUDITOR_GROUP not in grupos:
            raise PermissionError("El usuario no pertenece al grupo auditor.")
        return subject


@lru_cache(maxsize=1)
def get_cognito_auditor_jwt_validator() -> CognitoAuditorJwtValidator:
    return CognitoAuditorJwtValidator()
