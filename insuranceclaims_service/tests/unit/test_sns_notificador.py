"""HU4.2.2 · Adaptador SNS Mobile Push (FCM v1) con botocore Stubber: mensaje, endpoint existente y errores."""
import json

import boto3
from botocore.stub import ANY, Stubber

from src.application.ports.notificador_push import ResultadoEnvio
from src.infrastructure.notifications.sns_notificador import SnsNotificador

APP_ARN = "arn:aws:sns:us-east-1:000000000000:app/GCM/solventa-dev-fcm"
ENDPOINT_ARN = "arn:aws:sns:us-east-1:000000000000:endpoint/GCM/solventa-dev-fcm/1234abcd"
TOKEN = "fcm-token-de-prueba-" + "x" * 60 + "ABC123"
DATOS = {"tipo": "SINIESTRO_ESTADO", "siniestro_id": "s-1", "numero": "SIN-2026-1", "estado": "EN_EVALUACION", "evento_id": "e-1"}


def _notificador():
    cliente = boto3.client("sns", region_name="us-east-1", aws_access_key_id="prueba", aws_secret_access_key="prueba")
    return SnsNotificador(APP_ARN, "us-east-1", client=cliente), Stubber(cliente)


def _atributos(stub, enabled="true", token=TOKEN):
    stub.add_response(
        "get_endpoint_attributes", {"Attributes": {"Enabled": enabled, "Token": token}}, {"EndpointArn": ENDPOINT_ARN}
    )


async def test_publica_un_mensaje_solo_de_datos_fcm_v1(caplog):
    notificador, stub = _notificador()
    stub.add_response("create_platform_endpoint", {"EndpointArn": ENDPOINT_ARN}, {"PlatformApplicationArn": APP_ARN, "Token": TOKEN})
    _atributos(stub)
    stub.add_response("publish", {"MessageId": "m-1"}, {"TargetArn": ENDPOINT_ARN, "MessageStructure": "json", "Message": ANY})

    with stub:
        resultado = await notificador.enviar(TOKEN, "ANDROID", DATOS)
        stub.assert_no_pending_responses()

    assert resultado == ResultadoEnvio.ENVIADO
    assert TOKEN not in caplog.text


async def test_el_cuerpo_tiene_data_y_prioridad_alta():
    notificador, stub = _notificador()
    publicados = []
    stub.add_response("create_platform_endpoint", {"EndpointArn": ENDPOINT_ARN})
    _atributos(stub)
    stub.add_response("publish", {"MessageId": "m-1"})

    original = notificador._client.publish

    def capturar(**kwargs):
        publicados.append(kwargs)
        return original(**kwargs)

    notificador._client.publish = capturar
    with stub:
        await notificador.enviar(TOKEN, "ANDROID", DATOS)

    gcm = json.loads(json.loads(publicados[0]["Message"])["GCM"])
    assert gcm == {"fcmV1Message": {"message": {"data": DATOS, "android": {"priority": "high"}}}}


async def test_endpoint_existente_deshabilitado_se_reutiliza_y_se_habilita():
    notificador, stub = _notificador()
    stub.add_client_error(
        "create_platform_endpoint", service_error_code="InvalidParameter",
        service_message=f"Invalid parameter: Token Reason: Endpoint {ENDPOINT_ARN} already exists with the same Token, but different attributes.",
    )
    _atributos(stub, enabled="false")
    stub.add_response("set_endpoint_attributes", {}, {"EndpointArn": ENDPOINT_ARN, "Attributes": {"Token": TOKEN, "Enabled": "true"}})
    stub.add_response("publish", {"MessageId": "m-2"})

    with stub:
        assert await notificador.enviar(TOKEN, "ANDROID", DATOS) == ResultadoEnvio.ENVIADO
        stub.assert_no_pending_responses()


async def test_endpoint_deshabilitado_al_publicar_es_token_invalido():
    notificador, stub = _notificador()
    stub.add_response("create_platform_endpoint", {"EndpointArn": ENDPOINT_ARN})
    _atributos(stub)
    stub.add_client_error("publish", service_error_code="EndpointDisabled")

    with stub:
        assert await notificador.enviar(TOKEN, "ANDROID", DATOS) == ResultadoEnvio.TOKEN_INVALIDO


async def test_otros_errores_son_transitorios_y_no_borran_el_token():
    for codigo in ("InvalidParameter", "AuthorizationError", "Throttling", "KMSAccessDenied"):
        notificador, stub = _notificador()
        stub.add_response("create_platform_endpoint", {"EndpointArn": ENDPOINT_ARN})
        _atributos(stub)
        stub.add_client_error("publish", service_error_code=codigo)
        with stub:
            assert await notificador.enviar(TOKEN, "ANDROID", DATOS) == ResultadoEnvio.ERROR_TRANSITORIO, codigo


async def test_sin_permiso_para_crear_el_endpoint_es_transitorio():
    notificador, stub = _notificador()
    stub.add_client_error("create_platform_endpoint", service_error_code="AuthorizationError", service_message="not authorized")

    with stub:
        assert await notificador.enviar(TOKEN, "ANDROID", DATOS) == ResultadoEnvio.ERROR_TRANSITORIO


async def test_plataforma_no_soportada():
    notificador, _ = _notificador()

    assert await notificador.enviar(TOKEN, "IOS", DATOS) == ResultadoEnvio.TOKEN_INVALIDO
