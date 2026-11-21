import uuid

import pytest

from src.domain.siniestros.entities import Siniestro
from src.domain.siniestros.errores import TransicionInvalida
from tests.fakes import AHORA


def siniestro(estado: str = "REPORTADO") -> Siniestro:
    return Siniestro(
        poliza_id=uuid.uuid4(), tipo="ROBO", estado=estado, clave_idempotencia="k",
        ocurrido_en=AHORA, reportado_en=AHORA,
    )


@pytest.mark.parametrize("inicial,nuevo", [
    ("REPORTADO", "EN_EVALUACION"), ("EN_EVALUACION", "APROBADO"),
    ("EN_EVALUACION", "RECHAZADO"), ("APROBADO", "PAGADO"),
])
def test_transiciones_validas_actualizan_estado_y_fecha(inicial, nuevo):
    claim = siniestro(inicial)

    assert claim.cambiar_estado(nuevo, AHORA) is True
    assert claim.estado == nuevo
    assert claim.estado_actualizado_en == AHORA


def test_mismo_estado_es_idempotente():
    claim = siniestro()
    assert claim.cambiar_estado("REPORTADO", AHORA) is False
    assert claim.estado_actualizado_en is None


def test_transicion_invalida_no_modifica_el_siniestro():
    claim = siniestro("REPORTADO")
    with pytest.raises(TransicionInvalida):
        claim.cambiar_estado("PAGADO", AHORA)
    assert claim.estado == "REPORTADO"
