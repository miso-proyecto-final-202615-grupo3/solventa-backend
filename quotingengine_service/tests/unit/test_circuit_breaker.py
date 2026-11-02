from src.infrastructure.resilience.circuit_breaker import CircuitBreaker, EstadoCircuito


class Reloj:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_abre_tras_umbral_de_fallas():
    reloj = Reloj()
    cb = CircuitBreaker(failure_threshold=2, recovery_seconds=10, clock=reloj)
    cb.registrar_falla()
    assert cb.permitir()
    cb.registrar_falla()

    assert cb.estado == EstadoCircuito.ABIERTO
    assert not cb.permitir()


def test_semi_abierto_permite_un_solo_intento_y_cierra_con_exito():
    reloj = Reloj()
    cb = CircuitBreaker(failure_threshold=1, recovery_seconds=10, clock=reloj)
    cb.registrar_falla()
    reloj.t = 11

    assert cb.estado == EstadoCircuito.SEMI_ABIERTO
    assert cb.permitir()
    assert not cb.permitir()
    cb.registrar_exito()
    assert cb.estado == EstadoCircuito.CERRADO
    assert cb.permitir()


def test_falla_en_semi_abierto_reabre_el_circuito():
    reloj = Reloj()
    cb = CircuitBreaker(failure_threshold=3, recovery_seconds=10, clock=reloj)
    for _ in range(3):
        cb.registrar_falla()
    reloj.t = 11
    assert cb.permitir()
    cb.registrar_falla()

    assert cb.estado == EstadoCircuito.ABIERTO


def test_exito_reinicia_contador_de_fallas():
    cb = CircuitBreaker(failure_threshold=2, recovery_seconds=10)
    cb.registrar_falla()
    cb.registrar_exito()
    cb.registrar_falla()

    assert cb.estado == EstadoCircuito.CERRADO
