import uuid

import pytest
from botocore.exceptions import ClientError

from src.domain.verificaciones_kyc_aml.entities import ArchivoDocumento
from src.domain.verificaciones_kyc_aml.repositories import AlmacenamientoDocumentosError
from src.infrastructure.storage.documento_verificacion_s3_repository import (
    S3DocumentoVerificacionRepository,
)

JPEG = ArchivoDocumento(b"\xff\xd8\xff-frontal", "image/jpeg")
PNG = ArchivoDocumento(b"\x89PNG\r\n\x1a\n-reverso", "image/png")


class FakeS3:
    def __init__(self, error=None):
        self.objetos = []
        self.error = error

    def put_object(self, **kwargs):
        if self.error:
            raise self.error
        self.objetos.append(kwargs)


async def test_guarda_por_cliente_y_verificacion_con_cifrado_kms():
    s3 = FakeS3()
    repo = S3DocumentoVerificacionRepository(
        bucket="privado", kms_key_id="arn:aws:kms:key", client=s3
    )
    cliente_id, verificacion_id = uuid.uuid4(), uuid.uuid4()

    rutas = await repo.guardar(cliente_id, verificacion_id, JPEG, PNG)

    base = f"verificaciones-kyc-aml/{cliente_id}/{verificacion_id}"
    assert rutas.frontal == f"s3://privado/{base}/documento-frontal.jpg"
    assert rutas.reverso == f"s3://privado/{base}/documento-reverso.png"
    assert [o["Key"] for o in s3.objetos] == [
        f"{base}/documento-frontal.jpg",
        f"{base}/documento-reverso.png",
    ]
    assert all(o["Bucket"] == "privado" for o in s3.objetos)
    assert all(o["ServerSideEncryption"] == "aws:kms" for o in s3.objetos)
    assert all(o["SSEKMSKeyId"] == "arn:aws:kms:key" for o in s3.objetos)
    assert s3.objetos[1]["ContentType"] == "image/png"


async def test_sin_kms_usa_cifrado_administrado_por_s3():
    s3 = FakeS3()
    repo = S3DocumentoVerificacionRepository(bucket="privado", kms_key_id="", client=s3)

    await repo.guardar(uuid.uuid4(), uuid.uuid4(), JPEG, PNG)

    assert s3.objetos[0]["ServerSideEncryption"] == "AES256"
    assert "SSEKMSKeyId" not in s3.objetos[0]


async def test_falla_si_no_hay_bucket_configurado():
    repo = S3DocumentoVerificacionRepository(bucket="", client=FakeS3())
    repo.bucket = ""

    with pytest.raises(AlmacenamientoDocumentosError):
        await repo.guardar(uuid.uuid4(), uuid.uuid4(), JPEG, PNG)


async def test_errores_de_s3_se_traducen():
    error = ClientError({"Error": {"Code": "AccessDenied", "Message": "no"}}, "PutObject")
    repo = S3DocumentoVerificacionRepository(bucket="privado", client=FakeS3(error))

    with pytest.raises(AlmacenamientoDocumentosError):
        await repo.guardar(uuid.uuid4(), uuid.uuid4(), JPEG, PNG)
