"""Puerto del bus durable de eventos paramétricos (HU4.2.3, ASR-ESC-002).

La ingesta publica el evento y solo responde a la fuente cuando el bus confirmó que lo guardó.
Adaptador `sqs` (diseño de la wiki); sin bus configurado la tabla `evento_externo` hace de bus (`postgres`).
"""
from typing import Protocol


class BusNoDisponible(Exception):
    """El bus no confirmó el mensaje: la fuente debe reintentar (503)."""


class BusEventosParametricos(Protocol):
    async def publicar(self, mensaje: dict, correlation_id: str) -> None: ...

    async def aclose(self) -> None: ...
