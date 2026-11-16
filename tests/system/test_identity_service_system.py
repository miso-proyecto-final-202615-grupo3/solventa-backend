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
URL_VERIFICACIONES_KYC_AML = (
    f"{IDENTITY_SERVICE_URL}/clientes/{{cliente_id}}/verificaciones-kyc-aml"
)
VERIFICACIONES_ACTIVAS = True
TIMEOUT_SEGUNDOS = 15
DATOS_CLIENTE_REGISTRADO = None
CLIENTE_REGISTRADO = None
TOKEN_ACCESO = None
CLIENTE_ID_VERIFICACION_KYC_AML = None
VERIFICACION_KYC_AML_ID = None


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
    if "files" in kwargs:
        print("Archivos enviados:")
        for campo, archivo in kwargs["files"].items():
            nombre, contenido, tipo = archivo
            print(
                f"  {campo}: nombre={nombre}, content_type={tipo}, "
                f"tamaño={len(contenido)} bytes"
            )

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


def _registrar_y_autenticar_cliente():
    global CLIENTE_REGISTRADO, DATOS_CLIENTE_REGISTRADO, TOKEN_ACCESO

    DATOS_CLIENTE_REGISTRADO = _datos_cliente()
    registro = _enviar("POST", URL_REGISTRO, json=DATOS_CLIENTE_REGISTRADO)
    _verificar(registro.status_code == 201,
               "el registro del cliente responde HTTP 201")
    if registro.status_code != 201:
        return

    CLIENTE_REGISTRADO = registro.json()
    _verificar(bool(CLIENTE_REGISTRADO.get("id")),
               "la respuesta de registro incluye el identificador del cliente")
    if not CLIENTE_REGISTRADO.get("id"):
        return

    autenticacion = _enviar(
        "POST",
        URL_AUTENTICAR,
        json={
            "correo": DATOS_CLIENTE_REGISTRADO["correo"],
            "password": DATOS_CLIENTE_REGISTRADO["password"],
        },
    )
    _verificar(autenticacion.status_code == 200,
               "la autenticación responde HTTP 200")
    if autenticacion.status_code != 200:
        return

    TOKEN_ACCESO = autenticacion.json().get("access_token")
    _verificar(bool(TOKEN_ACCESO), "la respuesta incluye un access token")


def _cabeceras_autorizacion():
    _verificar(bool(TOKEN_ACCESO),
               "existe un token de acceso para la solicitud")
    return {"Authorization": f"Bearer {TOKEN_ACCESO or ''}"}


def test_case_1_autenticar_y_obtener_perfil():
    """Obtiene el perfil del cliente autenticado en la precondición."""
    _verificar(CLIENTE_REGISTRADO is not None,
               "existe un cliente registrado")
    if CLIENTE_REGISTRADO is None or not CLIENTE_REGISTRADO.get("id"):
        return

    response = _enviar(
        "GET",
        URL_PERFIL.format(cliente_id=CLIENTE_REGISTRADO["id"]),
        headers=_cabeceras_autorizacion(),
    )
    _verificar(response.status_code == 200,
               "la consulta de perfil responde HTTP 200")
    if response.status_code == 200:
        _verificar(response.json().get("id") == CLIENTE_REGISTRADO["id"],
                   "el perfil corresponde al cliente registrado")


def test_case_2_revocar_consentimiento_y_denegar_perfil():
    """Revoca el consentimiento del cliente autenticado y comprueba el bloqueo."""
    _verificar(CLIENTE_REGISTRADO is not None,
               "existe un cliente registrado")
    if CLIENTE_REGISTRADO is None or not CLIENTE_REGISTRADO.get("id"):
        return

    cliente_id = CLIENTE_REGISTRADO["id"]
    headers = _cabeceras_autorizacion()
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


def test_case_3_iniciar_verificaciones_kyc_aml():
    """Inicia KYC/AML para el cliente preparado en la precondición."""
    global CLIENTE_ID_VERIFICACION_KYC_AML, VERIFICACION_KYC_AML_ID

    _verificar(CLIENTE_REGISTRADO is not None,
               "existe un cliente registrado para KYC/AML")
    if CLIENTE_REGISTRADO is None or not CLIENTE_REGISTRADO.get("id"):
        return
    CLIENTE_ID_VERIFICACION_KYC_AML = CLIENTE_REGISTRADO["id"]
    VERIFICACION_KYC_AML_ID = None
    if CLIENTE_ID_VERIFICACION_KYC_AML is None:
        return

    archivos = {
        "documento_frontal": (
            "documento-frontal.jpg",
            b"\xff\xd8\xff" + os.urandom(1024),
            "image/jpeg",
        ),
        "documento_reverso": (
            "documento-reverso.png",
            b"\x89PNG\r\n\x1a\n" + os.urandom(1024),
            "image/png",
        ),
    }
    response = _enviar(
        "POST",
        URL_VERIFICACIONES_KYC_AML.format(
            cliente_id=CLIENTE_ID_VERIFICACION_KYC_AML
        ),
        files=archivos,
    )
    _verificar(response.status_code == 202,
               "el inicio de verificaciones KYC/AML responde HTTP 202")
    if response.status_code != 202:
        return

    resultado = response.json()
    verificacion_id = resultado.get("verificacion_id")
    try:
        uuid.UUID(verificacion_id)
        identificador_valido = True
    except (AttributeError, TypeError, ValueError):
        identificador_valido = False
    _verificar(identificador_valido,
               "la respuesta incluye un identificador de verificación válido")
    _verificar(resultado.get("estado") == "INICIADA",
               "la respuesta indica que la verificación fue iniciada")
    _verificar(bool(resultado.get("fecha")),
               "la respuesta incluye la fecha de inicio")
    if identificador_valido:
        VERIFICACION_KYC_AML_ID = verificacion_id


def test_case_4_consultar_resultado_verificaciones_kyc_aml():
    """Consulta y valida el resultado KYC/AML del intento iniciado en el caso 4."""
    _verificar(
        CLIENTE_ID_VERIFICACION_KYC_AML is not None
        and VERIFICACION_KYC_AML_ID is not None,
        "hay un cliente y una verificación guardados para consultar",
    )
    if (
        CLIENTE_ID_VERIFICACION_KYC_AML is None
        or VERIFICACION_KYC_AML_ID is None
    ):
        return

    response = _enviar(
        "GET",
        f"{URL_VERIFICACIONES_KYC_AML.format(cliente_id=CLIENTE_ID_VERIFICACION_KYC_AML)}"
        f"/{VERIFICACION_KYC_AML_ID}",
    )
    _verificar(response.status_code == 200,
               "la consulta de verificaciones KYC/AML responde HTTP 200")
    if response.status_code != 200:
        return

    resultado = response.json()
    _verificar(
        resultado.get("verificacion_id") == VERIFICACION_KYC_AML_ID,
        "la respuesta corresponde al identificador de verificación guardado",
    )
    _verificar(
        resultado.get("cliente_id") == CLIENTE_ID_VERIFICACION_KYC_AML,
        "la respuesta corresponde al identificador del cliente registrado",
    )
    _verificar(resultado.get("estado") == "APROBADO",
               "el estado de las verificaciones es APROBADO")
    _verificar(resultado.get("resultado_kyc") == "APROBADO",
               "el resultado de KYC es APROBADO")
    _verificar(resultado.get("resultado_aml") == "APROBADO",
               "el resultado de AML es APROBADO")


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
    precondicion_exitosa = _ejecutar_caso(
        "Precondición: registrar y autenticar cliente",
        _registrar_y_autenticar_cliente,
    )
    resultados = []
    if precondicion_exitosa:
        resultados = [
            _ejecutar_caso(
                "Test Case 1: autenticación y perfil",
                test_case_1_autenticar_y_obtener_perfil,
            ),
            _ejecutar_caso(
                "Test Case 2: revocación y acceso denegado",
                test_case_2_revocar_consentimiento_y_denegar_perfil,
            ),
            _ejecutar_caso(
                "Test Case 3: iniciar verificaciones KYC/AML",
                test_case_3_iniciar_verificaciones_kyc_aml,
            ),
            _ejecutar_caso(
                "Test Case 4: consultar resultado de KYC/AML",
                test_case_4_consultar_resultado_verificaciones_kyc_aml,
            ),
        ]
    if VERIFICACIONES_ACTIVAS and (
        not precondicion_exitosa or not all(resultados)
    ):
        sys.exit(1)
