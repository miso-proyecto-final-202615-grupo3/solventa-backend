"""Elige el adaptador de notificaciones push por `NOTIFICADOR_PUSH` (HU4.2.2, decisión N2)."""
from src.application.ports.notificador_push import NotificadorPush
from src.infrastructure.notifications.registro_notificador import RegistroNotificador
from src.infrastructure.notifications.sns_notificador import SnsNotificador


def crear_notificador_push(settings) -> NotificadorPush:
    tipo = settings.NOTIFICADOR_PUSH.lower()
    if tipo == "registro":
        return RegistroNotificador()
    if tipo == "sns":
        return SnsNotificador(settings.SNS_PLATFORM_APPLICATION_ARN, settings.AWS_REGION, settings.SNS_AWS_PROFILE)
    raise ValueError(f"NOTIFICADOR_PUSH no soportado: {settings.NOTIFICADOR_PUSH}")
