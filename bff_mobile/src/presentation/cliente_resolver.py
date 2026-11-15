"""Resuelve el `cliente_id` a partir del correo del token (HU4.1.1).

Caché en memoria por correo con TTL (`CLIENTE_ID_CACHE_SECONDS`): evita consultar a Identidad
en cada request de siniestros. Nunca registra el correo.
"""
import time

from src.core.config import settings
from src.infrastructure.gateways.identity_service_gateway import IdentityGatewayError, IdentityServiceGateway
from src.presentation.errors import ApiError

_cache: dict[str, tuple[float, str]] = {}


def limpiar_cache() -> None:
    _cache.clear()


class ClienteIdResolver:
    def __init__(self, gateway: IdentityServiceGateway, ttl_seconds: int | None = None) -> None:
        self.gateway = gateway
        self.ttl_seconds = settings.CLIENTE_ID_CACHE_SECONDS if ttl_seconds is None else ttl_seconds

    async def resolver(self, correo: str, correlation_id: str) -> str:
        clave = correo.strip().lower()
        ahora = time.monotonic()
        guardado = _cache.get(clave)
        if guardado and ahora - guardado[0] < self.ttl_seconds:
            return guardado[1]
        try:
            cliente_id = await self.gateway.obtener_cliente_id(correo, correlation_id)
        except IdentityGatewayError as exc:
            if exc.status_code == 404:
                raise ApiError(404, "CLIENTE_NO_REGISTRADO", "No encontramos tu cuenta.") from exc
            raise ApiError(503, "SERVICIO_NO_DISPONIBLE", "El servicio no está disponible.") from exc
        _cache[clave] = (ahora, cliente_id)
        return cliente_id
