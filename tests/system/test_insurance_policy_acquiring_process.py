import base64
import json
import os
import sys
import time
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

import requests
from dotenv import load_dotenv

SERVICE_PREFIX_MAP = {
    "bff-web": "/api/v1/bff-web",
    "identity-service": "/api/v1/identity-service",
    "quotingengine-service": "/api/v1/quotingengine-service",
    "insurancepolicies-service": "/api/v1/insurancepolicies-service",
    "payments-service": "/api/v1/payments-service",
}

ENVIRONMENT_MAP = {
    "local": {
        "identity-service": "SYSTEM_TESTS_IDENTITY_SERVICE_BASE_URL",
        "quotingengine-service": "SYSTEM_TESTS_QUOTINGENGINE_SERVICE_BASE_URL",
        "insurancepolicies-service": "SYSTEM_TESTS_INSURANCEPOLICIES_SERVICE_BASE_URL",
        "payments-service": "SYSTEM_TESTS_PAYMENTS_SERVICE_BASE_URL",
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
    PAYMENTS_SERVICE_URL = IDENTITY_SERVICE_URL
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
    PAYMENTS_SERVICE_BASE_URL = _base_url(
        ENVIRONMENT_MAP["local"]["payments-service"]
    )
else:
    base_url = _base_url(ENVIRONMENT_MAP[ENTORNO])
    IDENTITY_SERVICE_BASE_URL = base_url
    QUOTINGENGINE_SERVICE_BASE_URL = base_url
    INSURANCEPOLICIES_SERVICE_BASE_URL = base_url
    PAYMENTS_SERVICE_BASE_URL = base_url

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
    PAYMENTS_SERVICE_URL = (
        PAYMENTS_SERVICE_BASE_URL + SERVICE_PREFIX_MAP["payments-service"]
    )

URL_REGISTRO = f"{IDENTITY_SERVICE_URL}/clientes/registro"
URL_AUTENTICAR = f"{IDENTITY_SERVICE_URL}/clientes/autenticar"
URL_PRODUCTO = f"{QUOTINGENGINE_SERVICE_URL}/productos/VIDA_HIPOTECARIO"
URL_COTIZACIONES = f"{QUOTINGENGINE_SERVICE_URL}/cotizaciones"
URL_CONDICIONES = f"{URL_COTIZACIONES}/{{cotizacion_id}}/condiciones"
URL_DECISIONES = f"{URL_CONDICIONES}/decisiones"
URL_VERIFICACIONES_KYC_AML = (
    f"{IDENTITY_SERVICE_URL}/clientes/{{cliente_id}}/verificaciones-kyc-aml"
)
URL_FIRMA_DIGITAL = (
    f"{INSURANCEPOLICIES_SERVICE_URL}/cotizaciones/{{cotizacion_id}}/firma-digital"
)
URL_RESUMEN_PAGO = (
    f"{PAYMENTS_SERVICE_URL}/cotizaciones/{{cotizacion_id}}/resumen-pago"
)
URL_PAGOS = f"{PAYMENTS_SERVICE_URL}/pagos"
URL_PAGO = f"{PAYMENTS_SERVICE_URL}/pagos/{{pago_id}}"
URL_POLIZA_POR_COTIZACION = (
    f"{INSURANCEPOLICIES_SERVICE_URL}/cotizaciones/{{cotizacion_id}}/poliza"
)
URL_CERTIFICADO = f"{INSURANCEPOLICIES_SERVICE_URL}/polizas/{{poliza_id}}/certificado"
URL_DESCARGA_CERTIFICADO = f"{URL_CERTIFICADO}/descarga"

CODIGO_PRODUCTO = "VIDA_HIPOTECARIO"
TIMEOUT_SEGUNDOS = 30
VERIFICACIONES_ACTIVAS = True
MAX_INTENTOS = 3

DATOS_CLIENTE_REGISTRADO = None
CLIENTE_REGISTRADO = None
TOKEN_ACCESO = None
PRODUCTO_CONSULTADO = None
PRODUCTO_ID = None
COTIZACION_CREADA = None
ID_COTIZACION = None
ID_VERIFICACION_KYC_AML = None
FIRMA_DIGITAL_CREADA = None
ID_FIRMA_DIGITAL = None
ID_PAGO = None
ID_CONDICIONES = None
ID_POLIZA = None


def _ocultar_datos(valor):
    if isinstance(valor, dict):
        return {
            clave: "[REDACTADO]"
            if clave.lower()
            in {
                "password",
                "access_token",
                "id_token",
                "refresh_token",
                "numero_tarjeta",
                "cvv",
            }
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
    tipo_contenido = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
    if tipo_contenido == "application/pdf":
        print(f"Contenido: PDF en memoria ({len(response.content)} bytes)")
    else:
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


def _iniciar_verificacion_kyc_aml():
    global ID_VERIFICACION_KYC_AML

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
        ID_VERIFICACION_KYC_AML = verificacion_id


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


def test_case_2_consultar_condiciones_cotizacion():
    """Consulta y almacena las condiciones de la cotización del cliente."""
    global ID_CONDICIONES

    _verificar(ID_COTIZACION is not None, "existe una cotización creada")
    _verificar(
        COTIZACION_CREADA["cliente_id"] == CLIENTE_REGISTRADO["id"],
        "la cotización pertenece al cliente autenticado",
    )
    _verificar(
        COTIZACION_CREADA["producto_codigo"] == CODIGO_PRODUCTO,
        "la cotización corresponde a VIDA_HIPOTECARIO",
    )
    response = _enviar(
        "GET",
        URL_CONDICIONES.format(cotizacion_id=ID_COTIZACION),
        headers=_cabeceras_autorizacion(),
    )
    _verificar(
        response.status_code == 200,
        "la consulta de condiciones responde HTTP 200",
    )
    if response.status_code != 200:
        return

    condiciones = response.json()
    _verificar(
        condiciones.get("cotizacion_id") == ID_COTIZACION,
        "las condiciones corresponden a la cotización creada",
    )
    ID_CONDICIONES = condiciones.get("condiciones_cotizacion_id")
    _verificar(bool(ID_CONDICIONES), "la respuesta incluye el ID de condiciones")


def test_case_3_decidir_condiciones_cotizacion():
    """Acepta las condiciones consultadas."""
    _verificar(bool(ID_CONDICIONES), "existen condiciones consultadas")
    response = _enviar(
        "POST",
        URL_DECISIONES.format(cotizacion_id=ID_COTIZACION),
        json={
            "condiciones_cotizacion_id": ID_CONDICIONES,
            "decision": "ACEPTADA",
        },
        headers=_cabeceras_autorizacion(),
    )
    _verificar(
        response.status_code == 201,
        "la decisión ACEPTADA responde HTTP 201",
    )
    if response.status_code != 201:
        return

    resultado = response.json()
    _verificar(
        resultado.get("decision") == "ACEPTADA",
        "la respuesta registra la decisión ACEPTADA",
    )
    _verificar(
        resultado.get("condiciones_cotizacion_id") == ID_CONDICIONES,
        "la decisión corresponde a las condiciones consultadas",
    )
    _verificar(
        resultado.get("cliente_id") == CLIENTE_REGISTRADO["id"],
        "la decisión corresponde al cliente autenticado",
    )


def test_case_4_iniciar_verificaciones_kyc_aml():
    """Inicia y conserva el primer intento de verificación KYC/AML."""
    _iniciar_verificacion_kyc_aml()


def test_case_5_consultar_resultado_kyc_aml():
    """Consulta y valida el resultado del primer intento KYC/AML."""
    _consultar_resultado_kyc_aml(ID_VERIFICACION_KYC_AML, 5)


def test_case_6_capturar_firma_digital():
    """Captura y conserva la firma manuscrita para la cotización creada."""
    global FIRMA_DIGITAL_CREADA, ID_FIRMA_DIGITAL

    _verificar(ID_COTIZACION is not None, "existe una cotización creada")
    _verificar(bool(PRODUCTO_ID), "existe el ID del producto cotizado")
    contenido_firma = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAACAAAAAQCAIAAAD4YuoOAAAAW0lEQVR4nLXUMQ4AIAgD"
        "QP7/aY1GHQgBhJbJhV6MiMiuQasVLbdYwDlxGB0HZ+wgIONFQJi4uclk28rMX0OBqVz8"
        "i6k/YJLpDmLIYD6UwyAXg8ngF5xiWIv6MRNLiG3ZsdldgQAAAABJRU5ErkJggg=="
    )
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


def test_case_7_consultar_resumen_y_pagar_con_tarjeta():
    """Consulta el resumen, paga con tarjeta y valida el estado del pago."""
    global ID_PAGO

    _verificar(ID_COTIZACION is not None, "existe una cotización creada")
    _verificar(
        CLIENTE_REGISTRADO is not None,
        "existe el cliente registrado para realizar el pago",
    )

    resumen_response = _enviar(
        "GET",
        URL_RESUMEN_PAGO.format(cotizacion_id=ID_COTIZACION),
        headers={
            **_cabeceras_autorizacion(),
            "X-Correlation-Id": str(uuid.uuid4()),
        },
    )
    _verificar(
        resumen_response.status_code == 200,
        "el resumen del pago responde HTTP 200",
    )
    if resumen_response.status_code != 200:
        return

    resumen = resumen_response.json()
    _verificar(
        resumen.get("cotizacion_id") == ID_COTIZACION,
        "el resumen corresponde a la cotización creada",
    )
    try:
        prima_total = Decimal(str(resumen.get("prima_total")))
        prima_valida = prima_total.is_finite() and prima_total > 0
    except InvalidOperation:
        prima_valida = False
        prima_total = Decimal("0")
    _verificar(prima_valida, "el resumen incluye una prima total válida")
    _verificar(
        isinstance(resumen.get("moneda"), str) and bool(resumen["moneda"]),
        "el resumen incluye la moneda del pago",
    )
    metodos_pago = resumen.get("metodos_pago")
    _verificar(
        isinstance(metodos_pago, list)
        and any(
            isinstance(metodo, dict)
            and metodo.get("codigo") == "TARJETA_CREDITO"
            for metodo in metodos_pago
        ),
        "el resumen incluye la tarjeta de crédito como método de pago",
    )
    _verificar(
        _fecha_iso_valida(resumen.get("expira_en")),
        "el resumen incluye una fecha de expiración válida",
    )

    pago_response = _enviar(
        "POST",
        URL_PAGOS,
        json={
            "cotizacion_id": ID_COTIZACION,
            "cliente_id": CLIENTE_REGISTRADO["id"],
            "metodo_pago": "TARJETA_CREDITO",
            "numero_tarjeta": "4242424242424242",
            "mes_expiracion": 12,
            "anio_expiracion": 2099,
            "cvv": "123",
        },
        headers={
            **_cabeceras_autorizacion(),
            "Idempotency-Key": f"pago-{uuid.uuid4().hex}",
            "X-Correlation-Id": str(uuid.uuid4()),
        },
    )
    _verificar(
        pago_response.status_code == 201,
        "el pago con tarjeta responde HTTP 201",
    )
    if pago_response.status_code != 201:
        return

    pago = pago_response.json()
    pago_id = pago.get("pago_id")
    try:
        uuid.UUID(pago_id)
        identificador_valido = True
    except (AttributeError, TypeError, ValueError):
        identificador_valido = False
    _verificar(identificador_valido, "la respuesta incluye un ID de pago válido")
    _verificar(
        pago.get("cotizacion_id") == ID_COTIZACION,
        "el pago corresponde a la cotización creada",
    )
    _verificar(
        pago.get("cliente_id") == CLIENTE_REGISTRADO["id"],
        "el pago corresponde al cliente registrado",
    )
    _verificar(
        pago.get("metodo_pago") == "TARJETA_CREDITO",
        "el pago se procesó con tarjeta de crédito",
    )
    _verificar(pago.get("estado") == "APROBADO", "el pago fue aprobado")
    _verificar(
        pago.get("tarjeta_ultimos4") == "4242",
        "la respuesta confirma los últimos cuatro dígitos de la tarjeta",
    )
    _verificar(
        pago.get("moneda") == resumen.get("moneda"),
        "el pago conserva la moneda del resumen",
    )
    try:
        monto_pago = Decimal(str(pago.get("monto")))
        monto_valido = monto_pago == prima_total.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    except InvalidOperation:
        monto_valido = False
    _verificar(monto_valido, "el monto cobrado coincide con la prima del resumen")
    _verificar(
        _fecha_iso_valida(pago.get("creado_en"))
        and _fecha_iso_valida(pago.get("procesado_en")),
        "la respuesta incluye fechas válidas de creación y procesamiento",
    )
    if identificador_valido:
        ID_PAGO = pago_id

    _verificar(ID_PAGO is not None, "hay un ID válido para consultar el pago")
    estado_response = _enviar(
        "GET",
        URL_PAGO.format(pago_id=ID_PAGO),
        headers={
            **_cabeceras_autorizacion(),
            "X-Correlation-Id": str(uuid.uuid4()),
        },
    )
    _verificar(
        estado_response.status_code == 200,
        "la consulta del estado del pago responde HTTP 200",
    )
    if estado_response.status_code != 200:
        return

    estado_pago = estado_response.json()
    _verificar(
        estado_pago.get("pago_id") == ID_PAGO,
        "la consulta corresponde al pago creado",
    )
    _verificar(
        estado_pago.get("estado") == "APROBADO",
        "el estado consultado del pago es APROBADO",
    )
    _verificar(
        estado_pago.get("monto") == pago.get("monto")
        and estado_pago.get("moneda") == pago.get("moneda"),
        "la consulta conserva el monto y la moneda del pago",
    )


def _cabeceras_poliza():
    _verificar(CLIENTE_REGISTRADO is not None, "existe el cliente registrado")
    return {
        **_cabeceras_autorizacion(),
        "X-Client-Id": CLIENTE_REGISTRADO["id"],
        "X-Correlation-Id": str(uuid.uuid4()),
    }


def _uuid_valido(valor):
    try:
        uuid.UUID(valor)
        return True
    except (AttributeError, TypeError, ValueError):
        return False


def test_case_8_consultar_poliza_por_cotizacion():
    """Espera la emisión de la póliza y conserva su identificador."""
    global ID_POLIZA

    _verificar(bool(ID_COTIZACION), "existe una cotización creada")
    cabeceras = _cabeceras_poliza()
    print("Esperando 5 segundos antes de consultar la póliza.")
    time.sleep(5)
    for intento in range(1, MAX_INTENTOS + 1):
        print(f"Consulta de póliza: intento {intento}/{MAX_INTENTOS}")
        response = _enviar(
            "GET",
            URL_POLIZA_POR_COTIZACION.format(cotizacion_id=ID_COTIZACION),
            headers=cabeceras,
        )
        if response.status_code == 404:
            resultado = response.json()
            _verificar(
                isinstance(resultado, dict)
                and isinstance(resultado.get("detail"), dict)
                and resultado["detail"].get("codigo") == "POLIZA_NO_ENCONTRADA",
                "la póliza aún no ha sido emitida",
            )
            if intento < MAX_INTENTOS:
                print("La póliza aún no está disponible; esperando 5 segundos.")
                time.sleep(5)
                continue
            _verificar(False, "la póliza fue emitida dentro del límite de intentos")
            return

        _verificar(response.status_code == 200, "la consulta de póliza responde HTTP 200")
        if response.status_code != 200:
            return
        poliza = response.json()
        _verificar(isinstance(poliza, dict), "la respuesta de póliza es un objeto")
        poliza_id = poliza.get("poliza_id")
        identificador_valido = _uuid_valido(poliza_id)
        _verificar(identificador_valido, "la respuesta incluye un ID de póliza válido")
        _verificar(
            poliza.get("cotizacion_id") == ID_COTIZACION,
            "la póliza corresponde a la cotización creada",
        )
        _verificar(poliza.get("estado") == "EMITIDA", "la póliza está EMITIDA")
        _verificar(
            isinstance(poliza.get("numero"), str) and bool(poliza["numero"]),
            "la póliza incluye su número",
        )
        _verificar(
            isinstance(poliza.get("titular_nombre"), str) and bool(poliza["titular_nombre"]),
            "la póliza incluye el nombre del titular",
        )
        _verificar(
            _fecha_iso_valida(poliza.get("vigencia_desde"))
            and _fecha_iso_valida(poliza.get("vigencia_hasta")),
            "la póliza incluye fechas de vigencia válidas",
        )
        try:
            prima = Decimal(str(poliza.get("prima")))
            prima_valida = prima.is_finite() and prima > 0
        except InvalidOperation:
            prima_valida = False
        _verificar(prima_valida, "la póliza incluye una prima válida")
        _verificar(
            poliza.get("moneda") is None
            or (isinstance(poliza.get("moneda"), str) and bool(poliza["moneda"])),
            "la moneda de la póliza es válida",
        )
        _verificar(
            poliza.get("estado_certificado") in {"PENDIENTE", "GENERADO"},
            "la póliza incluye un estado de certificado válido",
        )
        if identificador_valido:
            ID_POLIZA = poliza_id
        return


def test_case_9_consultar_estado_certificado():
    """Espera hasta que el certificado de la póliza esté generado."""
    _verificar(bool(ID_POLIZA), "existe un ID de póliza guardado")
    cabeceras = _cabeceras_poliza()
    print("Esperando 10 segundos antes de consultar el certificado.")
    time.sleep(10)
    for intento in range(1, MAX_INTENTOS + 1):
        print(f"Consulta de certificado: intento {intento}/{MAX_INTENTOS}")
        response = _enviar(
            "GET",
            URL_CERTIFICADO.format(poliza_id=ID_POLIZA),
            headers=cabeceras,
        )
        _verificar(
            response.status_code == 200,
            "la consulta del certificado responde HTTP 200",
        )
        if response.status_code != 200:
            return
        resultado = response.json()
        _verificar(isinstance(resultado, dict), "la respuesta de certificado es un objeto")
        _verificar(
            resultado.get("poliza_id") == ID_POLIZA,
            "el certificado corresponde a la póliza creada",
        )
        estado = resultado.get("estado_certificado")
        _verificar(
            estado in {"PENDIENTE", "GENERADO"},
            "el estado del certificado es válido",
        )
        _verificar(
            isinstance(resultado.get("disponible"), bool)
            and resultado["disponible"] == (estado == "GENERADO"),
            "la disponibilidad corresponde al estado del certificado",
        )
        if estado == "GENERADO":
            _verificar(True, "el certificado está GENERADO")
            return
        if intento < MAX_INTENTOS:
            print("El certificado aún está pendiente; esperando 10 segundos.")
            time.sleep(10)
    _verificar(False, "el certificado fue generado dentro del límite de intentos")


def test_case_10_descargar_certificado():
    """Descarga el certificado en memoria y comprueba su formato PDF."""
    _verificar(bool(ID_POLIZA), "existe un ID de póliza guardado")
    response = _enviar(
        "GET",
        URL_DESCARGA_CERTIFICADO.format(poliza_id=ID_POLIZA),
        headers=_cabeceras_poliza(),
    )
    _verificar(response.status_code == 200, "la descarga responde HTTP 200")
    if response.status_code != 200:
        return
    tipo_contenido = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
    _verificar(tipo_contenido == "application/pdf", "la respuesta tiene tipo application/pdf")
    _verificar(
        response.content.startswith(b"%PDF-") and response.content.rstrip().endswith(b"%%EOF"),
        "el certificado descargado contiene un PDF con encabezado y final válidos",
    )


def _fecha_iso_valida(valor):
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00")).tzinfo is not None
    except (AttributeError, TypeError, ValueError):
        return False


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
            ("Test Case 2: consultar condiciones de la cotización", test_case_2_consultar_condiciones_cotizacion),
            ("Test Case 3: aceptar condiciones", test_case_3_decidir_condiciones_cotizacion),
            ("Test Case 4: iniciar verificaciones KYC/AML", test_case_4_iniciar_verificaciones_kyc_aml),
            ("Test Case 5: consultar resultado KYC/AML", test_case_5_consultar_resultado_kyc_aml),
            ("Test Case 6: capturar firma digital", test_case_6_capturar_firma_digital),
            ("Test Case 7: consultar resumen y pagar con tarjeta", test_case_7_consultar_resumen_y_pagar_con_tarjeta),
            ("Test Case 8: consultar póliza por cotización", test_case_8_consultar_poliza_por_cotizacion),
            ("Test Case 9: consultar estado del certificado", test_case_9_consultar_estado_certificado),
            ("Test Case 10: descargar certificado PDF", test_case_10_descargar_certificado),
        ]
        resultados = [
            _ejecutar_caso(nombre, caso)
            for nombre, caso in casos
        ]

    if VERIFICACIONES_ACTIVAS and (
        not precondicion_exitosa or not all(resultados)
    ):
        sys.exit(1)
