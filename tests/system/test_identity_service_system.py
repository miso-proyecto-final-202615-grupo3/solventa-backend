import json
import os
import sys
import uuid
from pathlib import Path

import requests
from dotenv import load_dotenv

SERVICE_PREFIX_MAP = {
    "identity-service": "/api/v1/identity-service",
    "bff-web": "/api/v1/bff-web",
    "bff-mobile": "/api/v1/bff-mobile",
}

ENVIRONMENT_MAP = {
    "local": {
        "identity-service": "SYSTEM_TESTS_IDENTITY_SERVICE_BASE_URL",
        "bff-web": "SYSTEM_TESTS_BFF_WEB_BASE_URL",
        "bff-mobile": "SYSTEM_TESTS_BFF_MOBILE_BASE_URL",
    },
    "dev": "SYSTEM_TESTS_DEV_BASE_URL",
    "prod": "SYSTEM_TESTS_PROD_BASE_URL",
}

if (
    len(sys.argv) != 3
    or sys.argv[1] not in ENVIRONMENT_MAP
    or sys.argv[2] not in SERVICE_PREFIX_MAP
):
    print(
        f"Usage: python {sys.argv[0]} "
        "<local|dev|prod> <identity-service|bff-web|bff-mobile>"
    )
    sys.exit(1)

load_dotenv(Path(__file__).resolve().parent / ".env")

ENTORNO = sys.argv[1]
SERVICIO = sys.argv[2]
VARIABLE_BASE_URL = (
    ENVIRONMENT_MAP["local"][SERVICIO]
    if ENTORNO == "local"
    else ENVIRONMENT_MAP[ENTORNO]
)
BASE_URL = os.getenv(VARIABLE_BASE_URL)
if not BASE_URL:
    print(f"{VARIABLE_BASE_URL} no está definida en el entorno ni en .env")
    sys.exit(1)

IDENTITY_SERVICE_URL = BASE_URL.rstrip("/") + SERVICE_PREFIX_MAP[SERVICIO]

URL_REGISTRO = f"{IDENTITY_SERVICE_URL}/clientes/registro"
URL_AUTENTICAR = f"{IDENTITY_SERVICE_URL}/clientes/autenticar"
URL_PERFIL = f"{IDENTITY_SERVICE_URL}/clientes/{{cliente_id}}/perfil"
URL_CONSENTIMIENTO = (
    f"{IDENTITY_SERVICE_URL}/clientes/{{cliente_id}}/consentimiento"
)
VERIFICACIONES_ACTIVAS = True
TIMEOUT_SEGUNDOS = 15


def _ocultar_datos(valor):
    if isinstance(valor, dict):
        return {
            clave: "[REDACTADO]"
            if clave.lower() in {"password", "access_token", "id_token", "refresh_token"}
            else _ocultar_datos(contenido)
            for clave, contenido in valor.items()
        }
    if isinstance(valor, list):
        return [_ocultar_datos(elemento) for elemento in valor]
    return valor


def _enviar(metodo, url, **kwargs):
    print(f"\n>>> {metodo} {url}")
    headers = kwargs.get("headers", {})
    if headers:
        cabeceras = {
            clave: "Bearer [REDACTADO]"
            if clave.lower() == "authorization"
            else valor
            for clave, valor in headers.items()
        }
        print("Cabeceras:")
        print(json.dumps(cabeceras, indent=2, ensure_ascii=False))
    if "json" in kwargs:
        print("Petición:")
        print(json.dumps(_ocultar_datos(
            kwargs["json"]), indent=2, ensure_ascii=False))

    response = requests.request(
        metodo, url, timeout=TIMEOUT_SEGUNDOS, **kwargs)
    print(f"Respuesta: HTTP {response.status_code}")
    try:
        cuerpo = response.json()
    except ValueError:
        cuerpo = response.text
    print(json.dumps(_ocultar_datos(cuerpo), indent=2, ensure_ascii=False))
    return response


def _verificar(condicion, descripcion):
    resultado = "CORRECTO" if condicion else "FALLIDO"
    if not VERIFICACIONES_ACTIVAS:
        print(
            f"Verificación desactivada: {descripcion} (resultado observado: {resultado})")
        return

    print(f"Verificación {resultado}: {descripcion}")
    assert condicion, descripcion


def _datos_cliente():
    identificador = uuid.uuid4().hex
    return {
        "nombres": "Cliente",
        "apellidos": "Prueba Sistema",
        "tipo_documento": "CC",
        "numero_identificacion": str(uuid.uuid4().int)[:10],
        "correo": f"system-{identificador}@example.com",
        "password": "SystemTest123!",
        "consentimiento_datos": True,
        "fecha_nacimiento": "1990-05-15",
        "pais_residencia": "Colombia",
        "telefono": "+573001234567",
    }


def _registrar_cliente():
    datos = _datos_cliente()
    response = _enviar("POST", URL_REGISTRO, json=datos)
    _verificar(response.status_code == 201,
               "el registro del cliente responde HTTP 201")
    if response.status_code != 201:
        return None

    cliente = response.json()
    _verificar("id" in cliente,
               "la respuesta de registro incluye el identificador del cliente")
    return datos, cliente.get("id")


def _autenticar(datos):
    response = _enviar(
        "POST",
        URL_AUTENTICAR,
        json={"correo": datos["correo"], "password": datos["password"]},
    )
    _verificar(response.status_code == 200,
               "la autenticación responde HTTP 200")
    if response.status_code != 200:
        return None

    resultado = response.json()
    _verificar(bool(resultado.get("access_token")),
               "la respuesta incluye un access token")
    return resultado


def test_case_1_registrar_y_autenticar_cliente():
    """Registra un cliente y comprueba que luego pueda autenticarse."""
    datos = _datos_cliente()
    registro = _enviar("POST", URL_REGISTRO, json=datos)
    _verificar(registro.status_code == 201, "el registro responde HTTP 201")
    if registro.status_code != 201:
        return

    _autenticar(datos)


def test_case_2_autenticar_y_obtener_perfil():
    """Prepara un cliente, se autentica y comprueba que se obtiene su perfil."""
    cliente = _registrar_cliente()
    if cliente is None:
        return
    datos, cliente_id = cliente

    autenticacion = _autenticar(datos)
    if autenticacion is None or cliente_id is None:
        return

    response = _enviar(
        "GET",
        URL_PERFIL.format(cliente_id=cliente_id),
        headers={
            "Authorization": f"Bearer {autenticacion.get('access_token', '')}"},
    )
    _verificar(response.status_code == 200,
               "la consulta de perfil responde HTTP 200")
    if response.status_code == 200:
        _verificar(response.json().get("id") == cliente_id,
                   "el perfil corresponde al cliente registrado")


def test_case_3_revocar_consentimiento_y_denegar_perfil():
    """Revoca el consentimiento y comprueba que el perfil sea denegado."""
    cliente = _registrar_cliente()
    if cliente is None:
        return
    datos, cliente_id = cliente

    autenticacion = _autenticar(datos)
    if autenticacion is None or cliente_id is None:
        return

    headers = {
        "Authorization": f"Bearer {autenticacion.get('access_token', '')}"}
    revocacion = _enviar(
        "PUT",
        URL_CONSENTIMIENTO.format(cliente_id=cliente_id),
        json={"estado": "REVOCADO"},
        headers=headers,
    )
    _verificar(revocacion.status_code == 200,
               "la revocación responde HTTP 200")
    if revocacion.status_code == 200:
        _verificar(revocacion.json().get("estado") == "REVOCADO",
                   "el consentimiento queda revocado")

    perfil = _enviar(
        "GET",
        URL_PERFIL.format(cliente_id=cliente_id),
        headers=headers,
    )
    _verificar(perfil.status_code == 403,
               "el acceso al perfil responde HTTP 403 tras revocar")


def _ejecutar_caso(nombre, caso):
    print(f"\n{'=' * 72}\n{nombre}\n{'=' * 72}")
    try:
        caso()
    except (AssertionError, requests.RequestException, ValueError) as error:
        print(f"Caso fallido: {error}")
        return False
    print("Caso finalizado.")
    return True


if __name__ == "__main__":
    resultados = [
        _ejecutar_caso("Test Case 1: registro y autenticación",
                       test_case_1_registrar_y_autenticar_cliente),
        _ejecutar_caso("Test Case 2: autenticación y perfil",
                       test_case_2_autenticar_y_obtener_perfil),
        _ejecutar_caso("Test Case 3: revocación y acceso denegado",
                       test_case_3_revocar_consentimiento_y_denegar_perfil),
    ]
    if VERIFICACIONES_ACTIVAS and not all(resultados):
        sys.exit(1)
