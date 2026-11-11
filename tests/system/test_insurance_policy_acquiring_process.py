import json
import os
import sys
import uuid
from pathlib import Path

import requests
from dotenv import load_dotenv

SERVICE_PREFIX_MAP = {
    "bff-web": "/api/v1/bff-web",
    "identity-service": "/api/v1/identity-service",
    "quotingengine-service": "/api/v1/quotingengine-service",
    "insurancepolicies-service": "/api/v1/insurancepolicies-service",
}

ENVIRONMENT_MAP = {
    "local": {
        "identity-service": "SYSTEM_TESTS_IDENTITY_SERVICE_BASE_URL",
        "quotingengine-service": "SYSTEM_TESTS_QUOTINGENGINE_SERVICE_BASE_URL",
        "insurancepolicies-service": "SYSTEM_TESTS_INSURANCEPOLICIES_SERVICE_BASE_URL",
        "bff-web": "SYSTEM_TESTS_BFF_WEB_BASE_URL",
    },
    "dev": "SYSTEM_TESTS_DEV_BASE_URL",
    "prod": "SYSTEM_TESTS_PROD_BASE_URL",
}

if (
    len(sys.argv) != 3
    or sys.argv[1] not in ENVIRONMENT_MAP
    or sys.argv[2] not in {"insurancepolicies-service", "bff-web"}
):
    print(
        f"Usage: python {sys.argv[0]} "
        "<local|dev|prod> <insurancepolicies-service|bff-web>"
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


if SERVICIO == "bff-web":
    variable_base_url = (
        ENVIRONMENT_MAP["local"]["bff-web"]
        if ENTORNO == "local"
        else ENVIRONMENT_MAP[ENTORNO]
    )
    base_url = _base_url(variable_base_url)
    IDENTITY_SERVICE_URL = base_url + SERVICE_PREFIX_MAP["bff-web"]
    QUOTINGENGINE_SERVICE_URL = IDENTITY_SERVICE_URL
    INSURANCEPOLICIES_SERVICE_URL = IDENTITY_SERVICE_URL
elif ENTORNO == "local":
    IDENTITY_SERVICE_BASE_URL = _base_url(
        ENVIRONMENT_MAP["local"]["identity-service"]
    )
    QUOTINGENGINE_SERVICE_BASE_URL = _base_url(
        ENVIRONMENT_MAP["local"]["quotingengine-service"]
    )
    INSURANCEPOLICIES_SERVICE_BASE_URL = _base_url(
        ENVIRONMENT_MAP["local"]["insurancepolicies-service"]
    )
else:
    base_url = _base_url(ENVIRONMENT_MAP[ENTORNO])
    IDENTITY_SERVICE_BASE_URL = base_url
    QUOTINGENGINE_SERVICE_BASE_URL = base_url
    INSURANCEPOLICIES_SERVICE_BASE_URL = base_url

if SERVICIO == "insurancepolicies-service":
    IDENTITY_SERVICE_URL = (
        IDENTITY_SERVICE_BASE_URL + SERVICE_PREFIX_MAP["identity-service"]
    )
    QUOTINGENGINE_SERVICE_URL = (
        QUOTINGENGINE_SERVICE_BASE_URL
        + SERVICE_PREFIX_MAP["quotingengine-service"]
    )
    INSURANCEPOLICIES_SERVICE_URL = (
        INSURANCEPOLICIES_SERVICE_BASE_URL
        + SERVICE_PREFIX_MAP["insurancepolicies-service"]
    )

URL_REGISTRO = f"{IDENTITY_SERVICE_URL}/clientes/registro"
URL_AUTENTICAR = f"{IDENTITY_SERVICE_URL}/clientes/autenticar"
URL_PRODUCTO = f"{QUOTINGENGINE_SERVICE_URL}/productos/VIDA_HIPOTECARIO"
URL_COTIZACIONES = f"{QUOTINGENGINE_SERVICE_URL}/cotizaciones"
URL_VERIFICACIONES_KYC_AML = (
    f"{IDENTITY_SERVICE_URL}/clientes/{{cliente_id}}/verificaciones-kyc-aml"
)
URL_FIRMA_DIGITAL = (
    f"{INSURANCEPOLICIES_SERVICE_URL}/cotizaciones/{{cotizacion_id}}/firma-digital"
)

CODIGO_PRODUCTO = "VIDA_HIPOTECARIO"
TIMEOUT_SEGUNDOS = 30
VERIFICACIONES_ACTIVAS = True

DATOS_CLIENTE_REGISTRADO = None
CLIENTE_REGISTRADO = None
TOKEN_ACCESO = None
PRODUCTO_CONSULTADO = None
PRODUCTO_ID = None
COTIZACION_CREADA = None
ID_COTIZACION = None
ID_VERIFICACION_CASO_2 = None
ID_VERIFICACION_CASO_4 = None
FIRMA_DIGITAL_CREADA = None
ID_FIRMA_DIGITAL = None


def _ocultar_datos(valor):
    if isinstance(valor, dict):
        return {
            clave: "[REDACTADO]"
            if clave.lower()
            in {"password", "access_token", "id_token", "refresh_token"}
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
        print(json.dumps(_ocultar_datos(kwargs["json"]), indent=2, ensure_ascii=False))
    if "data" in kwargs:
        print("Campos del formulario:")
        print(json.dumps(kwargs["data"], indent=2, ensure_ascii=False))
    if "files" in kwargs:
        print("Archivos enviados:")
        archivos = kwargs["files"]
        if isinstance(archivos, dict):
            archivos = archivos.items()
        for campo, archivo in archivos:
            nombre, contenido, tipo = archivo
            print(
                f"  {campo}: nombre={nombre}, content_type={tipo}, "
                f"tamaño={len(contenido)} bytes"
            )

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
    _verificar(registro.status_code == 201, "el registro responde HTTP 201")
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
    _verificar(bool(TOKEN_ACCESO), "hay un token para autorizar la solicitud")
    return {"Authorization": f"Bearer {TOKEN_ACCESO}"}


def _archivos_kyc_aml():
    return {
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


def _iniciar_verificacion_kyc_aml(caso_numero):
    global ID_VERIFICACION_CASO_2, ID_VERIFICACION_CASO_4

    _verificar(
        CLIENTE_REGISTRADO is not None,
        "existe un cliente registrado para la verificación",
    )
    cliente_id = CLIENTE_REGISTRADO["id"]
    response = _enviar(
        "POST",
        URL_VERIFICACIONES_KYC_AML.format(cliente_id=cliente_id),
        files=_archivos_kyc_aml(),
        headers={
            **_cabeceras_autorizacion(),
            "Idempotency-Key": f"kyc-{uuid.uuid4().hex}",
            "X-Correlation-Id": str(uuid.uuid4()),
        },
    )
    _verificar(
        response.status_code == 202,
        "el inicio de verificaciones KYC/AML responde HTTP 202",
    )
    if response.status_code != 202:
        return

    resultado = response.json()
    verificacion_id = resultado.get("verificacion_id")
    try:
        uuid.UUID(verificacion_id)
        identificador_valido = True
    except (AttributeError, TypeError, ValueError):
        identificador_valido = False
    _verificar(identificador_valido, "la respuesta incluye un ID de verificación válido")
    _verificar(
        resultado.get("estado") == "INICIADA",
        "el estado de la verificación iniciada es INICIADA",
    )
    _verificar(bool(resultado.get("fecha")), "la respuesta incluye la fecha de inicio")
    if identificador_valido:
        if caso_numero == 2:
            ID_VERIFICACION_CASO_2 = verificacion_id
        else:
            ID_VERIFICACION_CASO_4 = verificacion_id


def _consultar_resultado_kyc_aml(verificacion_id, numero_caso):
    _verificar(bool(verificacion_id), "hay un ID de verificación guardado")
    cliente_id = CLIENTE_REGISTRADO["id"]
    response = _enviar(
        "GET",
        f"{URL_VERIFICACIONES_KYC_AML.format(cliente_id=cliente_id)}"
        f"/{verificacion_id}",
        headers={
            **_cabeceras_autorizacion(),
            "X-Correlation-Id": str(uuid.uuid4()),
        },
    )
    _verificar(
        response.status_code == 200,
        f"la consulta KYC/AML del caso {numero_caso} responde HTTP 200",
    )
    if response.status_code != 200:
        return

    resultado = response.json()
    _verificar(
        resultado.get("verificacion_id") == verificacion_id,
        "la respuesta corresponde al ID de verificación guardado",
    )
    _verificar(
        resultado.get("cliente_id") == cliente_id,
        "la respuesta corresponde al ID del cliente registrado",
    )
    _verificar(resultado.get("estado") == "APROBADO", "el estado es APROBADO")
    _verificar(
        resultado.get("resultado_kyc") == "APROBADO",
        "el resultado de KYC es APROBADO",
    )
    _verificar(
        resultado.get("resultado_aml") == "APROBADO",
        "el resultado de AML es APROBADO",
    )


def test_case_1_crear_solicitud_cotizacion():
    """Crea y conserva una cotización de VIDA_HIPOTECARIO para el cliente."""
    global COTIZACION_CREADA, ID_COTIZACION, PRODUCTO_CONSULTADO, PRODUCTO_ID

    _verificar(CLIENTE_REGISTRADO is not None, "existe el cliente registrado")
    producto_response = _enviar("GET", URL_PRODUCTO)
    _verificar(
        producto_response.status_code == 200,
        "la consulta del producto responde HTTP 200",
    )
    if producto_response.status_code != 200:
        return
    PRODUCTO_CONSULTADO = producto_response.json()
    PRODUCTO_ID = PRODUCTO_CONSULTADO.get("producto_id")
    _verificar(
        PRODUCTO_CONSULTADO.get("codigo") == CODIGO_PRODUCTO,
        "el producto consultado corresponde a VIDA_HIPOTECARIO",
    )
    _verificar(bool(PRODUCTO_ID), "la respuesta del producto incluye su ID")

    solicitud = {
        "cliente_id": CLIENTE_REGISTRADO["id"],
        "producto_codigo": CODIGO_PRODUCTO,
        "parametros": {
            "saldo_credito": 200000000,
            "ubicacion": {
                "municipio": "Bogotá D.C.",
                "zona": "URBANA",
                "estrato": 4,
            },
        },
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
    _verificar(bool(ID_COTIZACION), "la respuesta incluye el ID de la cotización")
    _verificar(
        COTIZACION_CREADA.get("cliente_id") == CLIENTE_REGISTRADO["id"],
        "la cotización corresponde al cliente autenticado",
    )
    _verificar(
        COTIZACION_CREADA.get("producto_codigo") == CODIGO_PRODUCTO,
        "el código del producto cotizado corresponde al solicitado",
    )


def test_case_2_iniciar_verificaciones_kyc_aml():
    """Inicia y conserva el primer intento de verificación KYC/AML."""
    _iniciar_verificacion_kyc_aml(2)


def test_case_3_consultar_resultado_kyc_aml():
    """Consulta y valida el resultado del primer intento KYC/AML."""
    _consultar_resultado_kyc_aml(ID_VERIFICACION_CASO_2, 3)


def test_case_4_iniciar_segunda_verificacion_kyc_aml():
    """Inicia y conserva el segundo intento de verificación KYC/AML."""
    _iniciar_verificacion_kyc_aml(4)


def test_case_5_consultar_segundo_resultado_kyc_aml():
    """Consulta y valida el resultado del segundo intento KYC/AML."""
    _consultar_resultado_kyc_aml(ID_VERIFICACION_CASO_4, 5)


def test_case_6_capturar_firma_digital():
    """Captura y conserva la firma manuscrita para la cotización creada."""
    global FIRMA_DIGITAL_CREADA, ID_FIRMA_DIGITAL

    _verificar(ID_COTIZACION is not None, "existe una cotización creada")
    _verificar(bool(PRODUCTO_ID), "existe el ID del producto cotizado")
    contenido_firma = b"\x89PNG\r\n\x1a\n" + os.urandom(1024)
    response = _enviar(
        "POST",
        URL_FIRMA_DIGITAL.format(cotizacion_id=ID_COTIZACION),
        data={
            "cliente_id": CLIENTE_REGISTRADO["id"],
            "producto_id": PRODUCTO_ID,
        },
        files=[
            ("firma", ("firma-manuscrita.png", contenido_firma, "image/png")),
        ],
        headers={
            **_cabeceras_autorizacion(),
            "Idempotency-Key": f"firma-{uuid.uuid4().hex}",
            "X-Correlation-Id": str(uuid.uuid4()),
        },
    )
    _verificar(
        response.status_code == 201,
        "la captura de firma digital responde HTTP 201",
    )
    if response.status_code != 201:
        return

    FIRMA_DIGITAL_CREADA = response.json()
    ID_FIRMA_DIGITAL = FIRMA_DIGITAL_CREADA.get("firma_id")
    try:
        uuid.UUID(ID_FIRMA_DIGITAL)
        identificador_valido = True
    except (AttributeError, TypeError, ValueError):
        identificador_valido = False
    _verificar(identificador_valido, "la respuesta incluye un ID de firma válido")
    _verificar(
        FIRMA_DIGITAL_CREADA.get("cotizacion_id") == ID_COTIZACION,
        "la firma corresponde a la cotización creada",
    )
    _verificar(
        FIRMA_DIGITAL_CREADA.get("cliente_id") == CLIENTE_REGISTRADO["id"],
        "la firma corresponde al cliente registrado",
    )
    _verificar(
        FIRMA_DIGITAL_CREADA.get("producto_id") == PRODUCTO_ID,
        "la firma corresponde al producto cotizado",
    )
    _verificar(
        FIRMA_DIGITAL_CREADA.get("estado") == "CAPTURADA",
        "el estado de la firma digital es CAPTURADA",
    )
    _verificar(
        FIRMA_DIGITAL_CREADA.get("tamano_bytes") == len(contenido_firma),
        "la respuesta confirma el tamaño de la firma enviada",
    )


def _ejecutar_caso(nombre, caso):
    print(f"\n{'=' * 72}\n{nombre}\n{'=' * 72}")
    try:
        caso()
    except (
        AssertionError,
        requests.RequestException,
        ValueError,
        KeyError,
        TypeError,
    ) as error:
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
        casos = [
            ("Test Case 1: crear solicitud de cotización", test_case_1_crear_solicitud_cotizacion),
            ("Test Case 2: iniciar verificaciones KYC/AML", test_case_2_iniciar_verificaciones_kyc_aml),
            ("Test Case 3: consultar resultado KYC/AML", test_case_3_consultar_resultado_kyc_aml),
            ("Test Case 4: iniciar segunda verificación KYC/AML", test_case_4_iniciar_segunda_verificacion_kyc_aml),
            ("Test Case 5: consultar segundo resultado KYC/AML", test_case_5_consultar_segundo_resultado_kyc_aml),
            ("Test Case 6: capturar firma digital", test_case_6_capturar_firma_digital),
        ]
        resultados = [
            _ejecutar_caso(nombre, caso)
            for nombre, caso in casos
        ]

    if VERIFICACIONES_ACTIVAS and (
        not precondicion_exitosa or not all(resultados)
    ):
        sys.exit(1)
