from datetime import timedelta

from src.domain.activacion_movil.entities import EstadoIntento


class PoliticaIntentos:
    """Regla de tres intentos dentro de una ventana móvil de 24 horas."""

    def __init__(
        self,
        max_intentos: int = 3,
        ventana: timedelta = timedelta(hours=24),
    ) -> None:
        if max_intentos <= 0:
            raise ValueError("max_intentos debe ser mayor que cero.")
        if ventana <= timedelta():
            raise ValueError("ventana debe ser mayor que cero.")
        self.max_intentos = max_intentos
        self.ventana = ventana

    def cuenta(self, estado: EstadoIntento) -> bool:
        return estado in {EstadoIntento.RECHAZADO, EstadoIntento.EN_CURSO}

    def intentos_restantes(self, consumidos: int) -> int:
        return max(0, self.max_intentos - consumidos)

    def bloqueado(self, consumidos: int) -> bool:
        return consumidos >= self.max_intentos
