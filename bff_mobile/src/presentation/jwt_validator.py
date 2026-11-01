from dataclasses import dataclass

import jwt
from jwt import PyJWKClient
from functools import lru_cache

from pydantic import EmailStr, TypeAdapter, ValidationError

from src.core.config import settings


_EMAIL = TypeAdapter(EmailStr)


class InvalidJwtError(Exception):
    pass


@dataclass(frozen=True)
class ClienteAutenticado:
    correo: str
    subject: str


class CognitoJwtValidator:
    """Valida firma, emisor, vigencia y cliente de tokens emitidos por Cognito."""

    def __init__(self) -> None:
        if not settings.COGNITO_REGION or not settings.COGNITO_USER_POOL_ID:
            raise InvalidJwtError("Cognito no está configurado.")
        self._issuer = (
            f"https://cognito-idp.{settings.COGNITO_REGION}.amazonaws.com/"
            f"{settings.COGNITO_USER_POOL_ID}"
        )
        self._jwks = PyJWKClient(f"{self._issuer}/.well-known/jwks.json", cache_keys=True, lifespan=settings.COGNITO_JWKS_TTL_SECONDS)

    def validar(self, token: str) -> ClienteAutenticado:
        try:
            key = self._jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                issuer=self._issuer,
                options={"verify_aud": False},
            )
        except jwt.PyJWTError as exc:
            raise InvalidJwtError("Token inválido o vencido.") from exc

        token_use = claims.get("token_use")
        if token_use != "access" or claims.get("client_id") != settings.COGNITO_CLIENT_ID:
            raise InvalidJwtError("Tipo de token no permitido.")

        correo = claims.get("email") or claims.get("username")
        subject = claims.get("sub")
        if not isinstance(correo, str) or not isinstance(subject, str):
            raise InvalidJwtError("El token no contiene la identidad del cliente.")
        try:
            correo = _EMAIL.validate_python(correo)
        except ValidationError as exc:
            # En este pool el username es el correo; si no lo es, el token no sirve para activar.
            raise InvalidJwtError("La identidad del token no es un correo.") from exc
        return ClienteAutenticado(correo=correo, subject=subject)


@lru_cache(maxsize=1)
def get_cognito_jwt_validator() -> CognitoJwtValidator:
    return CognitoJwtValidator()
