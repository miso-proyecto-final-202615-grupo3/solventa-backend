import base64
import binascii
import json


def correo_desde_id_token(id_token: str | None) -> str | None:
    """Lee el claim `email` de un id_token de Cognito.

    No valida la firma: el token llega directo del MS Identidad por la red
    interna, justo después de autenticar. No usar con tokens enviados por el cliente.
    """
    if not id_token:
        return None
    partes = id_token.split(".")
    if len(partes) != 3:
        return None
    payload = partes[1] + "=" * (-len(partes[1]) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except (binascii.Error, ValueError):
        return None
    correo = claims.get("email") if isinstance(claims, dict) else None
    return correo if isinstance(correo, str) else None
