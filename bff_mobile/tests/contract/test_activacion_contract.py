import json
from pathlib import Path

from src.presentation.schemas import IniciarActivacionResponse, VerificarActivacionResponse


CONTRACTS = Path(__file__).resolve().parents[3] / "docs" / "contracts" / "activacion"


def test_respuesta_de_inicio_cumple_el_contrato_canonico():
    payload = json.loads((CONTRACTS / "inicio-frames.json").read_text(encoding="utf-8"))

    response = IniciarActivacionResponse.model_validate(payload)

    assert response.captura["tipo"] == "FRAMES"
    assert response.captura["reto"]["nonce"]


def test_respuesta_de_verificacion_cumple_el_contrato_canonico():
    payload = json.loads((CONTRACTS / "verificacion-aprobada.json").read_text(encoding="utf-8"))

    response = VerificarActivacionResponse.model_validate(payload)

    assert response.resultado == "APROBADO"
    assert response.dispositivo_vinculado is True
    assert response.intentos_restantes == 2
