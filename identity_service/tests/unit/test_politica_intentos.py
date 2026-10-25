from datetime import timedelta

import pytest

from src.domain.activacion_movil.entities import EstadoIntento
from src.domain.activacion_movil.politica_intentos import PoliticaIntentos


def test_cuenta_solo_rechazados_y_en_curso():
    politica = PoliticaIntentos()

    assert politica.cuenta(EstadoIntento.RECHAZADO) is True
    assert politica.cuenta(EstadoIntento.EN_CURSO) is True
    assert politica.cuenta(EstadoIntento.APROBADO) is False
    assert politica.cuenta(EstadoIntento.ANULADO) is False


def test_limita_a_tres_intentos_en_ventana_movil():
    politica = PoliticaIntentos()

    assert politica.intentos_restantes(0) == 3
    assert politica.intentos_restantes(2) == 1
    assert politica.intentos_restantes(3) == 0
    assert politica.intentos_restantes(4) == 0
    assert politica.bloqueado(2) is False
    assert politica.bloqueado(3) is True


@pytest.mark.parametrize(
    ("max_intentos", "ventana"),
    [(0, timedelta(hours=24)), (3, timedelta())],
)
def test_rechaza_configuracion_invalida(max_intentos, ventana):
    with pytest.raises(ValueError):
        PoliticaIntentos(max_intentos=max_intentos, ventana=ventana)
