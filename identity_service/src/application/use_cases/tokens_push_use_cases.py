"""Registro y consulta de tokens push (HU4.2.2, decisiones N4 y CA3).

El destino de una notificación siempre sale del cliente dueño del siniestro: un token solo puede estar en un
dispositivo `ACTIVO` a la vez, así que si otro cliente lo registra, deja de pertenecer al anterior.
"""
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from src.application.ports.tokens_push import DestinoPush, TokensPushRepository

logger = logging.getLogger(__name__)

PLATAFORMAS = {"ANDROID"}


class DispositivoNoVinculadoError(Exception):
    """La instalación no está vinculada (activa) al cliente."""


def final_token(token: str) -> str:
    """Únicos caracteres del token que se pueden registrar."""
    return token[-6:]


class RegistrarTokenPushUseCase:
    def __init__(self, repo: TokensPushRepository, reloj: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._repo = repo
        self._reloj = reloj

    async def ejecutar(self, cliente_id: uuid.UUID, installation_id: uuid.UUID, token: str, plataforma: str) -> None:
        if plataforma not in PLATAFORMAS:
            raise ValueError("plataforma no soportada")
        if not await self._repo.asignar_a_dispositivo_activo(cliente_id, installation_id, token, plataforma, self._reloj()):
            raise DispositivoNoVinculadoError()
        logger.info("token_push_registrado cliente_id=%s installation_id=%s token_final=%s", cliente_id, installation_id, final_token(token))


class EliminarTokenPushUseCase:
    def __init__(self, repo: TokensPushRepository) -> None:
        self._repo = repo

    async def de_dispositivo(self, cliente_id: uuid.UUID, installation_id: uuid.UUID) -> None:
        """Al cerrar sesión: idempotente."""
        await self._repo.quitar_de_dispositivo(cliente_id, installation_id)

    async def invalido(self, token: str) -> None:
        """El proveedor push informó que el token ya no existe (decisión N8)."""
        await self._repo.quitar_token(token)
        logger.info("token_push_invalido_eliminado token_final=%s", final_token(token))


class ListarDestinosPushUseCase:
    def __init__(self, repo: TokensPushRepository) -> None:
        self._repo = repo

    async def ejecutar(self, cliente_id: uuid.UUID) -> list[DestinoPush]:
        return await self._repo.destinos_de_cliente(cliente_id)
