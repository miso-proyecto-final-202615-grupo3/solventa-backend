import base64
import json

from src.presentation.id_token import correo_desde_id_token


def _segmento(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")


def test_extrae_el_claim_email():
    token = f"{_segmento({'alg': 'RS256'})}.{_segmento({'email': 'ana@example.com'})}.firma"

    assert correo_desde_id_token(token) == "ana@example.com"


def test_token_vacio_o_ausente_devuelve_none():
    assert correo_desde_id_token(None) is None
    assert correo_desde_id_token("") is None


def test_token_mal_formado_devuelve_none():
    assert correo_desde_id_token("no-es-un-jwt") is None
    assert correo_desde_id_token("a.%%%.c") is None


def test_token_sin_email_devuelve_none():
    token = f"{_segmento({'alg': 'RS256'})}.{_segmento({'sub': '123'})}.firma"

    assert correo_desde_id_token(token) is None
