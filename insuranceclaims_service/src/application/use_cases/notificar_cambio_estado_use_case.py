"""Envía la notificación de un cambio de estado a los dispositivos del dueño del siniestro (HU4.2.2, §5 paso 3).

El destino sale de `siniestro.cliente_id` (CA3), nunca del mensaje. Un error transitorio hace que el relay
reintente el evento ("al menos una vez"); un token inválido se elimina y se sigue con los demás.
"""
import logging

from src.application.ports.destinos_push import DestinosPush
from src.application.ports.notificador_push import NotificadorPush, ResultadoEnvio
from src.domain.siniestros.entities import EventoOutbox, Siniestro

logger = logging.getLogger(__name__)


class ErrorTransitorioPush(Exception):
    """Al menos un envío falló por una causa temporal: el evento debe reintentarse."""


class NotificarCambioEstadoUseCase:
    def __init__(self, destinos: DestinosPush, notificador: NotificadorPush) -> None:
        self.destinos = destinos
        self.notificador = notificador

    async def ejecutar(self, evento: EventoOutbox, siniestro: Siniestro) -> int:
        """Devuelve cuántos envíos se hicieron."""
        correlation_id = str(evento.evento_id)
        if siniestro.cliente_id is None:
            logger.warning("push_sin_dueno siniestro_id=%s evento_id=%s", siniestro.siniestro_id, evento.evento_id)
            return 0
        datos = {**evento.payload, "evento_id": str(evento.evento_id)}
        destinos = await self.destinos.listar(siniestro.cliente_id, correlation_id)
        enviados = 0
        transitorios = 0
        for destino in destinos:
            resultado = await self.notificador.enviar(destino.token, destino.plataforma, datos)
            if resultado == ResultadoEnvio.ENVIADO:
                enviados += 1
            elif resultado == ResultadoEnvio.TOKEN_INVALIDO:
                await self.destinos.eliminar(destino.token, correlation_id)
            else:
                transitorios += 1
        logger.info(
            "push_cambio_estado siniestro_id=%s evento_id=%s destinos=%s enviados=%s transitorios=%s",
            siniestro.siniestro_id, evento.evento_id, len(destinos), enviados, transitorios,
        )
        if transitorios:
            raise ErrorTransitorioPush(f"{transitorios} envío(s) con error transitorio")
        return enviados
