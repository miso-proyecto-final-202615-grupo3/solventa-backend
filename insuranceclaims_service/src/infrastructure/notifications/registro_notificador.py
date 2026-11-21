"""Adaptador local de notificaciones push (`NOTIFICADOR_PUSH=registro`): no envía nada fuera del servicio.

Sirve para probar el flujo completo sin Firebase ni SNS: deja una línea de log por envío (sin el token completo)
y guarda los envíos en memoria para las pruebas.
"""
import logging

from src.application.ports.notificador_push import NotificadorPush, ResultadoEnvio

logger = logging.getLogger(__name__)


class RegistroNotificador(NotificadorPush):
    def __init__(self) -> None:
        self.envios: list[dict] = []

    async def enviar(self, token: str, plataforma: str, datos: dict) -> ResultadoEnvio:
        self.envios.append({"token_final": token[-6:], "plataforma": plataforma, "datos": dict(datos)})
        logger.info(
            "push_registrado evento_id=%s siniestro_id=%s estado=%s token_final=%s",
            datos.get("evento_id"), datos.get("siniestro_id"), datos.get("estado"), token[-6:],
        )
        return ResultadoEnvio.ENVIADO
