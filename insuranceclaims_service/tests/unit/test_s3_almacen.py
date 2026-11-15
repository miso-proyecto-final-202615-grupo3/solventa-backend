import io
from datetime import UTC, datetime, timedelta

import boto3
import pytest
from botocore.config import Config
from botocore.stub import Stubber

from src.application.ports.almacen_evidencias import AlmacenNoDisponible
from src.infrastructure.storage.s3_almacen import S3AlmacenEvidencias

AHORA = datetime(2026, 11, 10, 20, 0, tzinfo=UTC)
CLAVE = "siniestros/s1/evidencias/e1.jpg"


def _cliente():
    return boto3.client(
        "s3", region_name="us-east-1", aws_access_key_id="prueba", aws_secret_access_key="prueba",
        config=Config(signature_version="s3v4"),
    )


async def test_carga_firmada_con_todas_las_condiciones():
    cliente = _cliente()
    almacen = S3AlmacenEvidencias("bucket-evidencias", "aws:kms", "arn:aws:kms:llave", cliente, reloj=lambda: AHORA)

    carga = await almacen.generar_carga(CLAVE, "image/jpeg", 5 * 1024 * 1024, timedelta(minutes=10))

    assert "bucket-evidencias" in carga.url
    assert carga.campos["key"] == CLAVE
    assert carga.campos["Content-Type"] == "image/jpeg"
    assert carga.campos["x-amz-server-side-encryption"] == "aws:kms"
    assert carga.campos["x-amz-server-side-encryption-aws-kms-key-id"] == "arn:aws:kms:llave"
    assert {"policy", "x-amz-signature", "x-amz-credential", "x-amz-algorithm", "x-amz-date"} <= set(carga.campos)
    assert carga.expira_en == AHORA + timedelta(minutes=10)

    import base64
    import json

    politica = json.loads(base64.b64decode(carga.campos["policy"]))
    condiciones = politica["conditions"]
    assert {"key": CLAVE} in condiciones
    assert ["content-length-range", 1, 5 * 1024 * 1024] in condiciones
    assert {"x-amz-server-side-encryption": "aws:kms"} in condiciones


async def test_sse_s3_sin_llave_kms():
    almacen = S3AlmacenEvidencias("b", "AES256", None, _cliente())

    carga = await almacen.generar_carga(CLAVE, "video/mp4", 10, timedelta(minutes=30))

    assert carga.campos["x-amz-server-side-encryption"] == "AES256"
    assert "x-amz-server-side-encryption-aws-kms-key-id" not in carga.campos


async def test_metadatos_y_objeto_inexistente():
    cliente = _cliente()
    almacen = S3AlmacenEvidencias("b", cliente_interno=cliente)
    with Stubber(cliente) as stub:
        stub.add_response(
            "head_object",
            {"ContentLength": 845123, "ContentType": "image/jpeg", "ServerSideEncryption": "aws:kms"},
            {"Bucket": "b", "Key": CLAVE},
        )
        stub.add_client_error("head_object", service_error_code="404", http_status_code=404)

        metadatos = await almacen.metadatos(CLAVE)
        inexistente = await almacen.metadatos("otra")

    assert (metadatos.tamano, metadatos.content_type, metadatos.cifrado) == (845123, "image/jpeg", "aws:kms")
    assert inexistente is None


async def test_lee_solo_los_primeros_bytes():
    cliente = _cliente()
    almacen = S3AlmacenEvidencias("b", cliente_interno=cliente)
    with Stubber(cliente) as stub:
        stub.add_response("get_object", {"Body": io.BytesIO(b"\xff\xd8\xff" + b"\x00" * 9)},
                          {"Bucket": "b", "Key": CLAVE, "Range": "bytes=0-11"})

        assert (await almacen.leer_inicio(CLAVE, 12))[:3] == b"\xff\xd8\xff"


@pytest.mark.parametrize("operacion", ["head_object", "delete_object"])
async def test_errores_del_almacen_son_no_disponible(operacion):
    cliente = _cliente()
    almacen = S3AlmacenEvidencias("b", cliente_interno=cliente)
    with Stubber(cliente) as stub:
        stub.add_client_error(operacion, service_error_code="AccessDenied", http_status_code=403)
        with pytest.raises(AlmacenNoDisponible):
            if operacion == "head_object":
                await almacen.metadatos(CLAVE)
            else:
                await almacen.eliminar(CLAVE)


def test_perfil_inexistente_es_no_disponible(monkeypatch):
    monkeypatch.setenv("AWS_PROFILE", "perfil-que-no-existe")

    with pytest.raises(AlmacenNoDisponible):
        S3AlmacenEvidencias.desde_configuracion("b", "us-east-1", "AES256", None, "http://minio:9000", None)


def test_perfil_vacio_se_ignora(monkeypatch):
    monkeypatch.setenv("AWS_PROFILE", "")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "prueba")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "prueba")

    almacen = S3AlmacenEvidencias.desde_configuracion("b", "us-east-1", "AES256", None, "http://minio:9000", None)

    assert almacen.bucket == "b"
