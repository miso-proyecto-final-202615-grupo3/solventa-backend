import json
import os
import sys
import uuid
from pathlib import Path

import requests
from dotenv import load_dotenv

SERVICE_PREFIX_MAP = {
    "bff-web": "/api/v1/bff-web",
    "bff-mobile": "/api/v1/bff-mobile",
    "identity-service": "/api/v1/identity-service",
    "quotingengine-service": "/api/v1/quotingengine-service"
}

ENVIRONMENT_MAP = {
    "local": {
        "identity-service": "SYSTEM_TESTS_IDENTITY_SERVICE_BASE_URL",
        "quotingengine-service": "SYSTEM_TESTS_QUOTINGENGINE_SERVICE_BASE_URL",
        "bff-web": "SYSTEM_TESTS_BFF_WEB_BASE_URL",
        "bff-mobile": "SYSTEM_TESTS_BFF_MOBILE_BASE_URL",
    },
    "dev": "SYSTEM_TESTS_DEV_BASE_URL",
    "prod": "SYSTEM_TESTS_PROD_BASE_URL",
}

if (
    len(sys.argv) != 3
    or sys.argv[1] not in ENVIRONMENT_MAP
    or sys.argv[2] not in {"quotingengine-service", "bff-web", "bff-mobile"}
):
    print(
        f"Usage: python {sys.argv[0]} "
        "<local|dev|prod> <quotingengine-service|bff-web|bff-mobile>"
    )
    sys.exit(1)

load_dotenv(Path(__file__).resolve().parent / ".env")
ENTORNO = sys.argv[1]
SERVICIO = sys.argv[2]


def _base_url(variable):
    base_url = os.getenv(variable)
    if not base_url:
        print(f"{variable} no está definida en el entorno ni en .env")
        sys.exit(1)
    return base_url.rstrip("/")


if ENTORNO == "local" and SERVICIO == "quotingengine-service":
    IDENTITY_SERVICE_BASE_URL = (
        _base_url(ENVIRONMENT_MAP["local"]["identity-service"])
    )
    QUOTINGENGINE_SERVICE_BASE_URL = (
        _base_url(ENVIRONMENT_MAP["local"]["quotingengine-service"])
    )
elif ENTORNO == "local" and SERVICIO in {"bff-web", "bff-mobile"}:
    base_url = _base_url(ENVIRONMENT_MAP["local"][SERVICIO])
    IDENTITY_SERVICE_BASE_URL = base_url
    QUOTINGENGINE_SERVICE_BASE_URL = base_url
elif ENTORNO in {"dev", "prod"}:
    base_url = _base_url(ENVIRONMENT_MAP[ENTORNO])
    IDENTITY_SERVICE_BASE_URL = base_url
    QUOTINGENGINE_SERVICE_BASE_URL = base_url

if SERVICIO == "quotingengine-service":
    IDENTITY_SERVICE_URL = (
        IDENTITY_SERVICE_BASE_URL + SERVICE_PREFIX_MAP["identity-service"]
    )
    QUOTINGENGINE_SERVICE_URL = (
        QUOTINGENGINE_SERVICE_BASE_URL +
        SERVICE_PREFIX_MAP["quotingengine-service"]
    )
elif SERVICIO in {"bff-web", "bff-mobile"}:
    IDENTITY_SERVICE_URL = (
        IDENTITY_SERVICE_BASE_URL
        + SERVICE_PREFIX_MAP[SERVICIO]
    )
    QUOTINGENGINE_SERVICE_URL = (
        QUOTINGENGINE_SERVICE_BASE_URL
        + SERVICE_PREFIX_MAP[SERVICIO]
    )

URL_REGISTRO = f"{IDENTITY_SERVICE_URL}/clientes/registro"
URL_AUTENTICAR = f"{IDENTITY_SERVICE_URL}/clientes/autenticar"
URL_PRODUCTO = f"{QUOTINGENGINE_SERVICE_URL}/productos/VIDA_HIPOTECARIO"
URL_COTIZACIONES = f"{QUOTINGENGINE_SERVICE_URL}/cotizaciones"
URL_COTIZACION = f"{URL_COTIZACIONES}/{{cotizacion_id}}"
VERIFICACIONES_ACTIVAS = True
TIMEOUT_SEGUNDOS = 15
CODIGO_PRODUCTO = "VIDA_HIPOTECARIO"

DATOS_CLIENTE_REGISTRADO = None
CLIENTE_REGISTRADO = None
TOKEN_ACCESO = None
COTIZACION_CREADA = None
ID_COTIZACION = None


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
            clave: "******" if clave.lower() == "authorization" else valor
            for clave, valor in headers.items()
        }
        print("Cabeceras:")
        print(json.dumps(cabeceras, indent=2, ensure_ascii=False))
    if "json" in kwargs:
        print("Petición:")
        print(json.dumps(_ocultar_datos(
            kwargs["json"]), indent=2, ensure_ascii=False))

    response = requests.request(
        metodo, url, timeout=TIMEOUT_SEGUNDOS, **kwargs
    )
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
            f"Verificación desactivada: {descripcion} "
            f"(resultado observado: {resultado})"
        )
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
    _verificar(
        registro.status_code == 201,
        "el registro del cliente responde HTTP 201",
    )
    CLIENTE_REGISTRADO = registro.json()
    _verificar(
        bool(CLIENTE_REGISTRADO.get("id")),
        "la respuesta de registro incluye el identificador del cliente",
    )

    autenticacion = _enviar(
        "POST",
        URL_AUTENTICAR,
        json={
            "correo": DATOS_CLIENTE_REGISTRADO["correo"],
            "password": DATOS_CLIENTE_REGISTRADO["password"],
        },
    )
    _verificar(
        autenticacion.status_code == 200,
        "la autenticación responde HTTP 200",
    )
    TOKEN_ACCESO = autenticacion.json().get("access_token")
    _verificar(bool(TOKEN_ACCESO), "la respuesta incluye un access token")


def _cabeceras_autorizacion():
    _verificar(bool(TOKEN_ACCESO),
               "existe un token de acceso para la solicitud")
    return {"Authorization": f"Bearer {TOKEN_ACCESO}"}


def test_case_1_consultar_producto_vida_hipotecario():
    """Consulta el producto VIDA_HIPOTECARIO y valida sus datos principales."""
    response = _enviar("GET", URL_PRODUCTO)
    _verificar(
        response.status_code == 200,
        "la consulta del producto responde HTTP 200",
    )
    if response.status_code != 200:
        return

    producto = response.json()
    _verificar(producto.get("pais") == "CO",
               "el producto corresponde a Colombia")
    _verificar(
        producto.get("nombre") == "Seguro de vida hipotecario",
        "el producto tiene el nombre esperado",
    )


def test_case_2_crear_solicitud_cotizacion():
    """Crea y almacena una cotización de VIDA_HIPOTECARIO para el cliente preparado."""
    global COTIZACION_CREADA, ID_COTIZACION

    _verificar(CLIENTE_REGISTRADO is not None, "existe un cliente registrado")
    solicitud = {
        "cliente_id": CLIENTE_REGISTRADO["id"],
        "producto_codigo": CODIGO_PRODUCTO,
        "parametros": {"valor_vivienda": 200000000},
    }
    response = _enviar(
        "POST",
        URL_COTIZACIONES,
        json=solicitud,
        headers=_cabeceras_autorizacion(),
    )
    _verificar(
        response.status_code == 201,
        "la creación de la cotización responde HTTP 201",
    )
    if response.status_code != 201:
        return

    COTIZACION_CREADA = response.json()
    ID_COTIZACION = COTIZACION_CREADA.get("cotizacion_id")
    _verificar(bool(ID_COTIZACION),
               "la respuesta incluye el ID de la cotización")
    _verificar(
        COTIZACION_CREADA.get("producto_codigo") == CODIGO_PRODUCTO,
        "el código del producto cotizado corresponde al solicitado",
    )


def test_case_3_consultar_cotizacion_almacenada():
    """Consulta la cotización creada y valida que conserva producto y prima total."""
    _verificar(ID_COTIZACION is not None, "existe una cotización creada")
    response = _enviar(
        "GET",
        URL_COTIZACION.format(cotizacion_id=ID_COTIZACION),
        headers=_cabeceras_autorizacion(),
    )
    _verificar(
        response.status_code == 200,
        "la consulta de la cotización responde HTTP 200",
    )
    if response.status_code != 200:
        return

    cotizacion = response.json()
    _verificar(
        cotizacion.get(
            "producto_codigo") == COTIZACION_CREADA["producto_codigo"],
        "el código del producto consultado corresponde al de la solicitud",
    )
    _verificar(
        cotizacion.get("prima_total") == COTIZACION_CREADA["prima_total"],
        "la prima total consultada corresponde a la de la solicitud",
    )


def _ejecutar_caso(nombre, caso):
    print(f"\n{'=' * 72}\n{nombre}\n{'=' * 72}")
    try:
        caso()
    except (AssertionError, requests.RequestException, ValueError, KeyError) as error:
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
                "Test Case 1: consultar producto VIDA_HIPOTECARIO",
                test_case_1_consultar_producto_vida_hipotecario,
            ),
            _ejecutar_caso(
                "Test Case 2: crear solicitud de cotización",
                test_case_2_crear_solicitud_cotizacion,
            ),
            _ejecutar_caso(
                "Test Case 3: consultar cotización almacenada",
                test_case_3_consultar_cotizacion_almacenada,
            ),
        ]

    if VERIFICACIONES_ACTIVAS and (
        not precondicion_exitosa or not all(resultados)
    ):
        sys.exit(1)
