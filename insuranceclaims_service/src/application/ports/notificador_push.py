from abc import ABC, abstractmethod
from enum import StrEnum


class ResultadoEnvio(StrEnum):
    ENVIADO = "ENVIADO"
    TOKEN_INVALIDO = "TOKEN_INVALIDO"
    ERROR_TRANSITORIO = "ERROR_TRANSITORIO"


class NotificadorPush(ABC):
    @abstractmethod
    async def enviar(self, token: str, plataforma: str, datos: dict) -> ResultadoEnvio:
        raise NotImplementedError
