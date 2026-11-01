import json
from pathlib import Path

from src.presentation.schemas import (
    EstadoConsentimientoBiometricoResponse,
    RegistrarConsentimientoBiometricoRequest,
    RegistrarConsentimientoBiometricoResponse,
)


CONTRACTS = Path(__file__).resolve().parents[3] / "docs" / "contracts" / "consentimiento-biometrico"


def _muestra(nombre: str) -> dict:
    return json.loads((CONTRACTS / nombre).read_text(encoding="utf-8"))


def test_estado_otorgado_cumple_el_contrato_canonico():
    estado = EstadoConsentimientoBiometricoResponse.model_validate(_muestra("estado-otorgado.json"))

    assert estado.otorgado is True
    assert estado.version_aceptada == estado.version_vigente


def test_estado_sin_decision_cumple_el_contrato_canonico():
    estado = EstadoConsentimientoBiometricoResponse.model_validate(_muestra("estado-sin-decision.json"))

    assert estado.otorgado is False
    assert estado.version_aceptada is None
    assert estado.decidido_en is None


def test_solicitud_y_respuesta_de_registro_cumplen_el_contrato_canonico():
    solicitud = RegistrarConsentimientoBiometricoRequest.model_validate(_muestra("registro-request.json"))
    respuesta = RegistrarConsentimientoBiometricoResponse.model_validate(_muestra("registro-response.json"))

    assert solicitud.decision == respuesta.decision == "ACEPTADO"
    assert solicitud.version_terminos == respuesta.version_terminos
    assert solicitud.decidido_en.tzinfo is not None
