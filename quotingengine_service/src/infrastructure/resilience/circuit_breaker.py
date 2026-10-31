import time
from collections.abc import Callable
from enum import StrEnum


class EstadoCircuito(StrEnum):
    CERRADO = "CERRADO"
    ABIERTO = "ABIERTO"
    SEMI_ABIERTO = "SEMI_ABIERTO"


class CircuitBreaker:
    """Abre el circuito tras N fallas consecutivas y permite un intento de prueba
    cuando transcurre el tiempo de recuperación."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_seconds: float = 15.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_seconds = recovery_seconds
        self._clock = clock
        self._failures = 0
        self._opened_at: float | None = None
        self._probe_in_flight = False

    @property
    def estado(self) -> EstadoCircuito:
        if self._opened_at is None:
            return EstadoCircuito.CERRADO
        if self._clock() - self._opened_at >= self.recovery_seconds:
            return EstadoCircuito.SEMI_ABIERTO
        return EstadoCircuito.ABIERTO

    def permitir(self) -> bool:
        estado = self.estado
        if estado == EstadoCircuito.CERRADO:
            return True
        if estado == EstadoCircuito.SEMI_ABIERTO and not self._probe_in_flight:
            self._probe_in_flight = True
            return True
        return False

    def registrar_exito(self) -> None:
        self._failures = 0
        self._opened_at = None
        self._probe_in_flight = False

    def registrar_falla(self) -> None:
        self._failures += 1
        self._probe_in_flight = False
        if self._opened_at is not None or self._failures >= self.failure_threshold:
            self._opened_at = self._clock()
