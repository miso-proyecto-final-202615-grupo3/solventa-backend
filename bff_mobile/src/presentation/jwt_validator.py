import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

import httpx
import jwt
from jwt import PyJWKClient
from pydantic import EmailStr, TypeAdapter, ValidationError

from src.core.config import settings


_EMAIL = TypeAdapter(EmailStr)


class InvalidJwtError(Exception):
    pass


class IdentityLookupUnavailableError(Exception):
    """Cognito no respondió al consultar el correo del token (no es culpa del cliente)."""


@dataclass(frozen=True)
class ClienteAutenticado:
    correo: str
    subject: str


class CognitoUserInfo:
    """Obtiene el correo del dueño de un access token con `GetUser` de Cognito.

    El pool usa el correo como alias, así que el access token solo trae `sub` y `username` (UUID).
    `GetUser` es una API pública autenticada por el mismo token: no requiere credenciales IAM y,
    además, rechaza tokens revocados por un cierre de sesión global.
    """

    def __init__(self, region: str, timeout_seconds: float) -> None:
        self._url = f"https://cognito-idp.{region}.amazonaws.com/"
        self._timeout = timeout_seconds

    def correo(self, access_token: str) -> str | None:
        try:
            response = httpx.post(
                self._url,
                headers={
                    "Content-Type": "application/x-amz-json-1.1",
                    "X-Amz-Target": "AWSCognitoIdentityProviderService.GetUser",
                },
                json={"AccessToken": access_token},
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise IdentityLookupUnavailableError("Cognito no respondió.") from exc
        if response.status_code == 400:
            # NotAuthorizedException / UserNotFoundException: token revocado o usuario eliminado.
            raise InvalidJwtError("Cognito rechazó el token.")
        if response.status_code != 200:
            raise IdentityLookupUnavailableError(f"Cognito respondió {response.status_code}.")
        atributos = response.json().get("UserAttributes", [])
        return next((a.get("Value") for a in atributos if a.get("Name") == "email"), None)


class _CorreoCache:
    """Caché acotada `sub → correo` para no llamar a Cognito en cada request."""

    def __init__(self, ttl_seconds: int, max_items: int = 1024) -> None:
        self._ttl = ttl_seconds
        self._max = max_items
        self._items: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, subject: str) -> str | None:
        with self._lock:
            item = self._items.get(subject)
            if item is None or item[0] < time.monotonic():
                self._items.pop(subject, None)
                return None
            self._items.move_to_end(subject)
            return item[1]

    def put(self, subject: str, correo: str) -> None:
        with self._lock:
            self._items[subject] = (time.monotonic() + self._ttl, correo)
            self._items.move_to_end(subject)
            while len(self._items) > self._max:
                self._items.popitem(last=False)


class CognitoJwtValidator:
    """Valida firma, emisor, vigencia y cliente de tokens emitidos por Cognito."""

    def __init__(self, user_lookup: Callable[[str], str | None] | None = None) -> None:
        if not settings.COGNITO_REGION or not settings.COGNITO_USER_POOL_ID:
            raise InvalidJwtError("Cognito no está configurado.")
        self._issuer = (
            f"https://cognito-idp.{settings.COGNITO_REGION}.amazonaws.com/"
            f"{settings.COGNITO_USER_POOL_ID}"
        )
        self._jwks = PyJWKClient(f"{self._issuer}/.well-known/jwks.json", cache_keys=True, lifespan=settings.COGNITO_JWKS_TTL_SECONDS)
        self._user_lookup = user_lookup or CognitoUserInfo(
            settings.COGNITO_REGION, settings.COGNITO_USERINFO_TIMEOUT_SECONDS
        ).correo
        self._correos = _CorreoCache(settings.COGNITO_USERINFO_CACHE_SECONDS)

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

        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise InvalidJwtError("El token no contiene la identidad del cliente.")

        correo = self._correos.get(subject)
        if correo is None:
            correo = self._user_lookup(token)
            try:
                correo = _EMAIL.validate_python(correo)
            except ValidationError as exc:
                raise InvalidJwtError("El usuario del token no tiene un correo válido.") from exc
            self._correos.put(subject, correo)
        return ClienteAutenticado(correo=correo, subject=subject)


@lru_cache(maxsize=1)
def get_cognito_jwt_validator() -> CognitoJwtValidator:
    return CognitoJwtValidator()
