"""HU4.2.3 · El detalle de un siniestro paramétrico pasa por el BFF Móvil sin perder datos (docs/contracts/parametricos)."""
import json
from pathlib import Path

from src.presentation.schemas import SiniestroDetalleResponse

CONTRACTS = Path(__file__).resolve().parents[3] / "docs" / "contracts" / "parametricos"


def _muestra(nombre: str) -> dict:
    return json.loads((CONTRACTS / nombre).read_text(encoding="utf-8"))


def test_detalle_parametrico_con_indemnizacion():
    muestra = _muestra("detalle-siniestro-parametrico.json")

    respuesta = SiniestroDetalleResponse.model_validate(muestra).model_dump(mode="json")

    assert respuesta["canal"] == "PARAMETRICO"
    assert respuesta["indemnizacion"] == {"monto": "300000.00", "moneda": "COP", "estado": "PAGO_SOLICITADO"}


def test_mensaje_push_parametrico_solo_texto():
    mensaje = _muestra("mensaje-siniestro-parametrico.json")

    assert mensaje["tipo"] == "SINIESTRO_ESTADO" and mensaje["canal"] == "PARAMETRICO"
    assert all(isinstance(valor, str) for valor in mensaje.values())  # FCM solo admite datos de texto
