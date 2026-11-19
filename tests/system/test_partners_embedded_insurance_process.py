"""Prueba de venta asistida mediante BFF Socios.

La precondición autentica al administrador mediante Identity Service a través
de BFF Web y crea el socio allí; las demás peticiones utilizan BFF Socios.
"""

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

ENVIRONMENT_MAP = {
    "local": {
        "socios": "SYSTEM_TESTS_BFF_SOCIOS_BASE_URL",
        "web": "SYSTEM_TESTS_BFF_WEB_BASE_URL",
    },
    "dev": "SYSTEM_TESTS_DEV_BASE_URL",
    "prod": "SYSTEM_TESTS_PROD_BASE_URL",
}
SOCIOS_PREFIX = "/api/v1/bff-socios"
WEB_PREFIX = "/api/v1/bff-web"
CODIGO_PRODUCTO = "VIDA_HIPOTECARIO"
TIMEOUT_SEGUNDOS = 30
MAX_INTENTOS = 3
ESPERA_SEGUNDOS = 10


def _variable(nombre):
    valor = os.getenv(nombre)
    if not valor:
        raise ValueError(f"{nombre} no está definida en el entorno ni en .env")
    return valor


def _urls(entorno):
    variables = ENVIRONMENT_MAP[entorno]
    if entorno == "local":
        socios_base = _variable(variables["socios"]).rstrip("/")
        web_base = _variable(variables["web"]).rstrip("/")
    else:
        socios_base = web_base = _variable(variables).rstrip("/")
    socios = socios_base + SOCIOS_PREFIX
    web = web_base + WEB_PREFIX
    return {
        "health": socios_base + "/health",
        "root": socios_base + "/",
        "autenticar": web + "/clientes/autenticar",
        "socios": web + "/socios",
        "api_keys": web + "/socios/{socio_id}/api-keys",
        "prospectos": socios + "/clientes/prospectos",
        "perfil": socios + "/clientes/{cliente_id}/perfil",
        "consentimiento": socios + "/clientes/{cliente_id}/consentimiento",
        "productos": socios + "/productos",
        "producto": socios + "/productos/{codigo}",
        "cotizaciones": socios + "/cotizaciones",
        "cotizacion": socios + "/cotizaciones/{cotizacion_id}",
        "condiciones": socios + "/cotizaciones/{cotizacion_id}/condiciones",
        "decisiones": socios + "/cotizaciones/{cotizacion_id}/condiciones/decisiones",
        "kyc": socios + "/clientes/{cliente_id}/verificaciones-kyc-aml",
        "firma": socios + "/cotizaciones/{cotizacion_id}/firma-digital",
        "resumen_pago": socios + "/cotizaciones/{cotizacion_id}/resumen-pago",
        "pagos": socios + "/pagos",
        "pago": socios + "/pagos/{pago_id}",
        "poliza_cotizacion": socios + "/cotizaciones/{cotizacion_id}/poliza",
        "poliza": socios + "/polizas/{poliza_id}",
        "mis_polizas": socios + "/polizas/mis-polizas",
        "certificado": socios + "/polizas/{poliza_id}/certificado",
        "descarga": socios + "/polizas/{poliza_id}/certificado/descarga",
    }


def _ocultar_datos(valor):
    if isinstance(valor, dict):
        return {
            clave: "[REDACTADO]"
            if clave.lower() in {
                "api_key", "authorization", "x-api-key", "numero_tarjeta", "cvv",
                "password", "access_token", "id_token", "refresh_token",
            }
            else _ocultar_datos(contenido)
            for clave, contenido in valor.items()
        }
    if isinstance(valor, list):
        return [_ocultar_datos(elemento) for elemento in valor]
    return valor


def _enviar(metodo, url, **kwargs):
    print(f"\n>>> {metodo} {url}")
    for clave, etiqueta in (("headers", "Cabeceras"), ("json", "Petición"), ("data", "Campos del formulario")):
        if clave in kwargs:
            print(f"{etiqueta}:\n{json.dumps(_ocultar_datos(kwargs[clave]), indent=2, ensure_ascii=False)}")
    if "files" in kwargs:
        print("Archivos enviados:")
        archivos = kwargs["files"]
        for campo, (nombre, contenido, tipo) in (
            archivos.items() if isinstance(archivos, dict) else archivos
        ):
            print(f"  {campo}: nombre={nombre}, content_type={tipo}, tamaño={len(contenido)} bytes")
    respuesta = requests.request(metodo, url, timeout=TIMEOUT_SEGUNDOS, **kwargs)
    print(f"Respuesta: HTTP {respuesta.status_code}")
    tipo = respuesta.headers.get("Content-Type", "").split(";")[0].strip().lower()
    if tipo == "application/pdf":
        print(f"Contenido: PDF en memoria ({len(respuesta.content)} bytes)")
    else:
        try:
            cuerpo = respuesta.json()
        except ValueError:
            cuerpo = respuesta.text
        print(json.dumps(_ocultar_datos(cuerpo), indent=2, ensure_ascii=False))
    return respuesta


def _verificar(condicion, descripcion):
    print(f"Verificación {'CORRECTO' if condicion else 'FALLIDO'}: {descripcion}")
    if not condicion:
        raise AssertionError(descripcion)


def _json(respuesta, estado, descripcion, tipo=dict):
    _verificar(respuesta.status_code == estado, f"{descripcion} responde HTTP {estado}")
    cuerpo = respuesta.json()
    _verificar(isinstance(cuerpo, tipo), f"{descripcion} devuelve un JSON válido")
    return cuerpo


def _uuid_valido(valor):
    try:
        uuid.UUID(valor)
        return True
    except (AttributeError, TypeError, ValueError):
        return False


def _fecha_valida(valor):
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00")).tzinfo is not None
    except (AttributeError, TypeError, ValueError):
        return False


def _monto_positivo(valor):
    try:
        monto = Decimal(str(valor))
        return monto.is_finite() and monto > 0
    except InvalidOperation:
        return False


class ProcesoSocios:
    def __init__(self, urls):
        self.urls = urls
        self.token_admin = None
        self.api_key = None
        self.socio_id = None
        self.cliente_id = None
        self.producto_id = None
        self.cotizacion_id = None
        self.condiciones_id = None
        self.verificacion_id = None
        self.firma_id = None
        self.pago_id = None
        self.poliza_id = None

    def url(self, nombre, **valores):
        return self.urls[nombre].format(**valores)

    def headers(self, cliente=True, idempotencia=None):
        _verificar(bool(self.api_key), "existe la API key del socio")
        headers = {"X-API-Key": self.api_key, "X-Correlation-Id": str(uuid.uuid4())}
        if cliente:
            _verificar(_uuid_valido(self.cliente_id), "existe el cliente vinculado")
            headers["X-Client-Id"] = self.cliente_id
        if idempotencia:
            headers["Idempotency-Key"] = f"{idempotencia}-{uuid.uuid4().hex}"
        return headers

    def precondicion(self):
        autenticacion = _json(
            _enviar(
                "POST",
                self.url("autenticar"),
                json={
                    "correo": _variable("SYSTEM_TESTS_SOCIOS_ADMIN_USER_EMAIL"),
                    "password": _variable("SYSTEM_TESTS_SOCIOS_ADMIN_USER_PASSWORD"),
                },
            ),
            200,
            "la autenticación del administrador",
        )
        self.token_admin = autenticacion.get("access_token")
        _verificar(
            isinstance(self.token_admin, str) and bool(self.token_admin.strip()),
            "la autenticación devuelve un access token válido",
        )
        identificador = uuid.uuid4().hex
        datos = {
            "nombre": f"Socio prueba {identificador}",
            "correo": f"socio-{identificador}@example.com",
            "tipo_socio": "BANCO",
            "canal_integracion": "API",
        }
        headers = {"Authorization": f"Bearer {self.token_admin}"}
        socio = _json(_enviar("POST", self.url("socios"), headers=headers, json=datos), 201, "el registro del socio")
        self.socio_id = socio.get("id")
        _verificar(_uuid_valido(self.socio_id), "el socio tiene un ID válido")
        _verificar(socio.get("correo") == datos["correo"] and socio.get("estado") == "ACTIVO", "el socio creado corresponde a la solicitud y está activo")
        clave = _json(
            _enviar("POST", self.url("api_keys", socio_id=self.socio_id), headers=headers),
            201, "la generación de API key",
        )
        _verificar(_uuid_valido(clave.get("api_key_id")), "la API key tiene un ID válido")
        self.api_key = clave.get("api_key")
        _verificar(isinstance(self.api_key, str) and bool(self.api_key), "la API key fue generada")

    def test_case_1_prospecto(self):
        identificador = uuid.uuid4().hex
        datos = {
            "nombres": "Cliente",
            "apellidos": "Prueba Sistema",
            "tipo_documento": "CC",
            "numero_identificacion": str(uuid.uuid4().int % 9000000000 + 1000000000),
            "correo": f"system-{identificador}@example.com",
            "consentimiento_datos": True,
            "fecha_nacimiento": "1990-05-15",
            "pais_residencia": "Colombia",
            "telefono": "+573001234567",
        }
        cliente = _json(_enviar("POST", self.url("prospectos"), headers=self.headers(cliente=False), json=datos), 201, "el registro del prospecto")
        self.cliente_id = cliente.get("id")
        _verificar(_uuid_valido(self.cliente_id), "el prospecto tiene un ID válido")
        _verificar(cliente.get("correo") == datos["correo"] and cliente.get("numero_identificacion") == datos["numero_identificacion"], "el prospecto corresponde a los datos enviados")
        perfil = _json(_enviar("GET", self.url("perfil", cliente_id=self.cliente_id), headers=self.headers()), 200, "la consulta del perfil")
        _verificar(perfil.get("id") == self.cliente_id, "el perfil corresponde al prospecto vinculado al socio")
        consentimiento = _json(
            _enviar("PUT", self.url("consentimiento", cliente_id=self.cliente_id), headers=self.headers(), json={"estado": "ACEPTADO"}),
            200, "la actualización del consentimiento",
        )
        _verificar(consentimiento.get("cliente_id") == self.cliente_id and consentimiento.get("estado") == "ACEPTADO", "el consentimiento del prospecto está aceptado")

    def test_case_2_catalogo(self):
        catalogo = _json(_enviar("GET", self.url("productos"), headers=self.headers(cliente=False)), 200, "el catálogo", list)
        productos = [p for p in catalogo if isinstance(p, dict) and p.get("codigo") == CODIGO_PRODUCTO]
        _verificar(len(productos) == 1 and _uuid_valido(productos[0].get("producto_id")), "el catálogo incluye el producto hipotecario con ID válido")
        producto = _json(_enviar("GET", self.url("producto", codigo=CODIGO_PRODUCTO), headers=self.headers(cliente=False)), 200, "la consulta del producto")
        self.producto_id = producto.get("producto_id")
        _verificar(producto.get("codigo") == CODIGO_PRODUCTO and self.producto_id == productos[0]["producto_id"], "el producto coincide con el catálogo")

    def test_case_3_cotizacion(self):
        solicitud = {
            "cliente_id": self.cliente_id,
            "producto_codigo": CODIGO_PRODUCTO,
            "parametros": {"saldo_credito": 200000000, "ubicacion": {"municipio": "Bogotá D.C.", "zona": "URBANA", "estrato": 4}},
        }
        cotizacion = _json(_enviar("POST", self.url("cotizaciones"), headers=self.headers(), json=solicitud), 201, "la creación de cotización")
        self.cotizacion_id = cotizacion.get("cotizacion_id")
        _verificar(_uuid_valido(self.cotizacion_id), "la cotización tiene un ID válido")
        _verificar(cotizacion.get("cliente_id") == self.cliente_id and cotizacion.get("producto_codigo") == CODIGO_PRODUCTO, "la cotización corresponde al cliente y producto")
        _verificar(_monto_positivo(cotizacion.get("prima_total")), "la cotización tiene una prima válida")
        consultada = _json(_enviar("GET", self.url("cotizacion", cotizacion_id=self.cotizacion_id), headers=self.headers()), 200, "la consulta de cotización")
        _verificar(consultada.get("cotizacion_id") == self.cotizacion_id and consultada.get("cliente_id") == self.cliente_id and consultada.get("producto_codigo") == CODIGO_PRODUCTO, "la cotización consultada coincide con la creada")

    def test_case_4_condiciones(self):
        valores = {"cotizacion_id": self.cotizacion_id}
        condiciones = _json(_enviar("GET", self.url("condiciones", **valores), headers=self.headers()), 200, "la consulta de condiciones")
        self.condiciones_id = condiciones.get("condiciones_cotizacion_id")
        _verificar(_uuid_valido(self.condiciones_id) and condiciones.get("cotizacion_id") == self.cotizacion_id, "las condiciones corresponden a la cotización")
        decision = _json(
            _enviar("POST", self.url("decisiones", **valores), headers=self.headers(), json={"condiciones_cotizacion_id": self.condiciones_id, "decision": "ACEPTADA"}),
            201, "la aceptación de condiciones",
        )
        _verificar(decision.get("decision") == "ACEPTADA" and decision.get("condiciones_cotizacion_id") == self.condiciones_id and decision.get("cliente_id") == self.cliente_id, "la decisión corresponde al cliente y las condiciones")

    def test_case_5_kyc(self):
        url = self.url("kyc", cliente_id=self.cliente_id)
        archivos = {
            "documento_frontal": ("documento-frontal.jpg", b"\xff\xd8\xff" + os.urandom(1024), "image/jpeg"),
            "documento_reverso": ("documento-reverso.png", b"\x89PNG\r\n\x1a\n" + os.urandom(1024), "image/png"),
        }
        inicio = _json(_enviar("POST", url, headers=self.headers(idempotencia="kyc"), data={"cotizacion_id": self.cotizacion_id}, files=archivos), 202, "el inicio KYC/AML")
        self.verificacion_id = inicio.get("verificacion_id")
        _verificar(_uuid_valido(self.verificacion_id) and inicio.get("estado") == "INICIADA" and _fecha_valida(inicio.get("fecha")), "la verificación fue iniciada con ID y fecha válidos")
        resultado = _json(_enviar("GET", f"{url}/{self.verificacion_id}", headers=self.headers()), 200, "la consulta KYC/AML")
        _verificar(resultado.get("verificacion_id") == self.verificacion_id and resultado.get("cliente_id") == self.cliente_id, "la verificación corresponde al cliente")
        _verificar(all(resultado.get(campo) == "APROBADO" for campo in ("estado", "resultado_kyc", "resultado_aml")), "KYC y AML están aprobados")

    def test_case_6_firma(self):
        contenido = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAACAAAAAQCAIAAAD4YuoOAAAAW0lEQVR4nLXUMQ4AIAgD"
            "QP7/aY1GHQgBhJbJhV6MiMiuQasVLbdYwDlxGB0HZ+wgIONFQJi4uclk28rMX0OBqVz8"
            "i6k/YJLpDmLIYD6UwyAXg8ngF5xiWIv6MRNLiG3ZsdldgQAAAABJRU5ErkJggg=="
        )
        url = self.url("firma", cotizacion_id=self.cotizacion_id)
        firma = _json(
            _enviar("POST", url, headers=self.headers(idempotencia="firma"), data={"cliente_id": self.cliente_id, "producto_id": self.producto_id}, files={"firma": ("firma.png", contenido, "image/png")}),
            201, "la captura de firma",
        )
        self.firma_id = firma.get("firma_id")
        _verificar(_uuid_valido(self.firma_id) and firma.get("estado") == "CAPTURADA" and firma.get("tamano_bytes") == len(contenido), "la firma fue capturada con ID y tamaño válidos")
        _verificar(firma.get("cliente_id") == self.cliente_id and firma.get("producto_id") == self.producto_id and firma.get("cotizacion_id") == self.cotizacion_id, "la firma corresponde al cliente, producto y cotización")
        consultada = _json(_enviar("GET", url, headers=self.headers()), 200, "la consulta de firma")
        _verificar(consultada.get("firma_id") == self.firma_id and consultada.get("estado") == "CAPTURADA", "la firma consultada coincide con la capturada")

    def test_case_7_pago(self):
        resumen = _json(_enviar("GET", self.url("resumen_pago", cotizacion_id=self.cotizacion_id), headers=self.headers()), 200, "el resumen de pago")
        _verificar(resumen.get("cotizacion_id") == self.cotizacion_id and _monto_positivo(resumen.get("prima_total")), "el resumen corresponde a la cotización y tiene una prima válida")
        _verificar(isinstance(resumen.get("moneda"), str) and bool(resumen["moneda"]) and _fecha_valida(resumen.get("expira_en")), "el resumen tiene moneda y fecha válidas")
        metodos = resumen.get("metodos_pago")
        _verificar(isinstance(metodos, list) and any(isinstance(m, dict) and m.get("codigo") == "TARJETA_CREDITO" for m in metodos), "el resumen admite tarjeta de crédito")
        pago = _json(
            _enviar("POST", self.url("pagos"), headers=self.headers(idempotencia="pago"), json={
                "cotizacion_id": self.cotizacion_id, "cliente_id": self.cliente_id,
                "metodo_pago": "TARJETA_CREDITO", "numero_tarjeta": "4242424242424242",
                "mes_expiracion": 12, "anio_expiracion": 2099, "cvv": "123",
            }),
            201, "el pago de la prima",
        )
        self.pago_id = pago.get("pago_id")
        _verificar(_uuid_valido(self.pago_id) and pago.get("estado") == "APROBADO", "el pago tiene ID válido y está aprobado")
        _verificar(pago.get("cliente_id") == self.cliente_id and pago.get("cotizacion_id") == self.cotizacion_id, "el pago corresponde al cliente y cotización")
        _verificar(pago.get("metodo_pago") == "TARJETA_CREDITO" and pago.get("tarjeta_ultimos4") == "4242" and pago.get("moneda") == resumen["moneda"], "el pago conserva el método y la moneda")
        _verificar(_monto_positivo(pago.get("monto")) and Decimal(str(pago["monto"])) == Decimal(str(resumen["prima_total"])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "el monto pagado coincide con la prima")
        _verificar(_fecha_valida(pago.get("creado_en")) and _fecha_valida(pago.get("procesado_en")), "el pago incluye fechas válidas")
        consultado = _json(_enviar("GET", self.url("pago", pago_id=self.pago_id), headers=self.headers()), 200, "la consulta de pago")
        _verificar(consultado.get("pago_id") == self.pago_id and consultado.get("cliente_id") == self.cliente_id and consultado.get("estado") == "APROBADO" and consultado.get("monto") == pago.get("monto") and consultado.get("moneda") == pago.get("moneda"), "el pago consultado coincide con el aprobado")

    def test_case_8_poliza(self):
        url = self.url("poliza_cotizacion", cotizacion_id=self.cotizacion_id)
        for intento in range(1, MAX_INTENTOS + 1):
            print(f"Consulta de póliza: intento {intento}/{MAX_INTENTOS}")
            respuesta = _enviar("GET", url, headers=self.headers())
            if respuesta.status_code == 404:
                cuerpo = respuesta.json()
                _verificar(isinstance(cuerpo, dict), "la respuesta de póliza pendiente es un objeto")
                detalle = cuerpo.get("detail")
                _verificar(isinstance(detalle, dict) and detalle.get("codigo") == "POLIZA_NO_ENCONTRADA", "la póliza aún no fue emitida")
                if intento < MAX_INTENTOS:
                    time.sleep(ESPERA_SEGUNDOS)
                    continue
                _verificar(False, "la póliza fue emitida dentro del límite de intentos")
            poliza = _json(respuesta, 200, "la consulta de póliza por cotización")
            self.poliza_id = poliza.get("poliza_id")
            _verificar(_uuid_valido(self.poliza_id) and poliza.get("cotizacion_id") == self.cotizacion_id and poliza.get("estado") == "EMITIDA", "la póliza emitida corresponde a la cotización")
            _verificar(isinstance(poliza.get("numero"), str) and bool(poliza["numero"]) and isinstance(poliza.get("titular_nombre"), str) and bool(poliza["titular_nombre"]), "la póliza incluye número y titular")
            _verificar(_fecha_valida(poliza.get("vigencia_desde")) and _fecha_valida(poliza.get("vigencia_hasta")) and _monto_positivo(poliza.get("prima")), "la póliza incluye vigencia y prima válidas")
            _verificar(poliza.get("estado_certificado") in {"PENDIENTE", "GENERADO"}, "la póliza incluye un estado de certificado válido")
            break
        detalle = _json(_enviar("GET", self.url("poliza", poliza_id=self.poliza_id), headers=self.headers()), 200, "la consulta de póliza por ID")
        _verificar(detalle.get("poliza_id") == self.poliza_id and detalle.get("cliente_id") == self.cliente_id and detalle.get("cotizacion_id") == self.cotizacion_id, "el detalle de póliza corresponde al cliente y cotización")
        lista = _json(_enviar("GET", self.url("mis_polizas"), headers=self.headers()), 200, "la consulta de pólizas del cliente", list)
        _verificar(any(isinstance(p, dict) and p.get("poliza_id") == self.poliza_id and p.get("cliente_id") == self.cliente_id for p in lista), "la póliza emitida aparece en las pólizas del cliente")

    def test_case_9_certificado(self):
        url = self.url("certificado", poliza_id=self.poliza_id)
        for intento in range(1, MAX_INTENTOS + 1):
            print(f"Consulta de certificado: intento {intento}/{MAX_INTENTOS}")
            certificado = _json(_enviar("GET", url, headers=self.headers()), 200, "la consulta del certificado")
            estado = certificado.get("estado_certificado")
            _verificar(certificado.get("poliza_id") == self.poliza_id and estado in {"PENDIENTE", "GENERADO"}, "el certificado corresponde a la póliza y tiene estado válido")
            _verificar(isinstance(certificado.get("disponible"), bool) and certificado["disponible"] == (estado == "GENERADO"), "la disponibilidad corresponde al estado")
            if estado == "GENERADO":
                break
            if intento < MAX_INTENTOS:
                time.sleep(ESPERA_SEGUNDOS)
        else:
            _verificar(False, "el certificado fue generado dentro del límite de intentos")
        respuesta = _enviar("GET", self.url("descarga", poliza_id=self.poliza_id), headers=self.headers())
        _verificar(respuesta.status_code == 200, "la descarga del certificado responde HTTP 200")
        _verificar(respuesta.headers.get("Content-Type", "").split(";")[0].strip().lower() == "application/pdf", "el certificado tiene tipo application/pdf")
        _verificar(respuesta.content.startswith(b"%PDF-") and respuesta.content.rstrip().endswith(b"%%EOF"), "el certificado descargado es un PDF válido")

    def test_case_10_salud(self):
        salud = _json(_enviar("GET", self.url("health")), 200, "la consulta de salud")
        _verificar(salud.get("status") == "ok", "el servicio está saludable")
        raiz = _json(_enviar("GET", self.url("root")), 200, "la consulta de raíz")
        _verificar(raiz.get("message") == "Solventa BFF Socios", "la raíz identifica BFF Socios")


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ENVIRONMENT_MAP:
        print(f"Usage: python {sys.argv[0]} <local|dev|prod>")
        return 1
    load_dotenv(Path(__file__).resolve().parent / ".env")
    try:
        proceso = ProcesoSocios(_urls(sys.argv[1]))
        casos = [
            ("Precondición: autenticar administrador, registrar socio y generar API key", proceso.precondicion),
            ("Test Case 1: registrar y vincular prospecto", proceso.test_case_1_prospecto),
            ("Test Case 2: consultar catálogo", proceso.test_case_2_catalogo),
            ("Test Case 3: cotizar", proceso.test_case_3_cotizacion),
            ("Test Case 4: aceptar condiciones", proceso.test_case_4_condiciones),
            ("Test Case 5: verificar identidad KYC/AML", proceso.test_case_5_kyc),
            ("Test Case 6: capturar firma digital", proceso.test_case_6_firma),
            ("Test Case 7: pagar prima inicial", proceso.test_case_7_pago),
            ("Test Case 8: consultar póliza emitida", proceso.test_case_8_poliza),
            ("Test Case 9: consultar y descargar certificado", proceso.test_case_9_certificado),
        ]
        if sys.argv[1] == "local":
            casos.append(("Test Case 10: consultar salud del servicio", proceso.test_case_10_salud))
        else:
            print("Las rutas / y /health de BFF Socios no están expuestas por el ingress compartido.")
        for nombre, caso in casos:
            print(f"\n{'=' * 72}\n{nombre}\n{'=' * 72}")
            caso()
            print("Caso finalizado.")
    except (AssertionError, requests.RequestException, ValueError, KeyError, TypeError) as error:
        print(f"Caso fallido: {error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
