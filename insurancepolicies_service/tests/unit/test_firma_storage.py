import os
import stat
import uuid

import pytest
from botocore.exceptions import ClientError

from src.domain.firmas.entities import ArchivoFirma, construir_ruta
from src.domain.firmas.repositories import AlmacenamientoFirmaError
from src.infrastructure.storage.firma_local_repository import (
    LocalAlmacenamientoFirmaRepository,
)
from src.infrastructure.storage.firma_s3_repository import S3AlmacenamientoFirmaRepository

ARCHIVO = ArchivoFirma(b"\x89PNG\r\n\x1a\n" + b"firma", "image/png")


def _ruta() -> str:
    return construir_ruta(uuid.uuid4(), uuid.uuid4(), "firma.png")


async def test_local_guarda_con_permisos_privados(tmp_path):
    repo = LocalAlmacenamientoFirmaRepository(tmp_path)
    ruta = _ruta()

    await repo.guardar(ruta, ARCHIVO)

    destino = tmp_path / ruta
    assert destino.read_bytes() == ARCHIVO.contenido
    if os.name != "nt":
        assert stat.S_IMODE(destino.stat().st_mode) == 0o600
        assert stat.S_IMODE(destino.parent.stat().st_mode) == 0o700
    assert ruta.startswith("firma-digital/")


async def test_local_no_sobrescribe_un_archivo_existente(tmp_path):
    repo = LocalAlmacenamientoFirmaRepository(tmp_path)
    ruta = _ruta()
    await repo.guardar(ruta, ARCHIVO)

    with pytest.raises(AlmacenamientoFirmaError):
        await repo.guardar(ruta, ARCHIVO)


async def test_local_rechaza_rutas_fuera_del_directorio(tmp_path):
    repo = LocalAlmacenamientoFirmaRepository(tmp_path)

    with pytest.raises(AlmacenamientoFirmaError):
        await repo.guardar("../fuera/firma.png", ARCHIVO)


async def test_local_no_sigue_enlaces_simbolicos(tmp_path):
    if os.name == "nt":
        pytest.skip("Windows requiere privilegios para crear enlaces simbólicos.")
    base = tmp_path / "base"
    base.mkdir()
    fuera = tmp_path / "fuera"
    fuera.mkdir()
    os.symlink(fuera, base / "firma-digital")
    repo = LocalAlmacenamientoFirmaRepository(base)

    with pytest.raises(AlmacenamientoFirmaError):
        await repo.guardar(_ruta(), ARCHIVO)
    assert list(fuera.iterdir()) == []


async def test_local_elimina_y_tolera_inexistente(tmp_path):
    repo = LocalAlmacenamientoFirmaRepository(tmp_path)
    ruta = _ruta()
    await repo.guardar(ruta, ARCHIVO)

    await repo.eliminar(ruta)
    await repo.eliminar(ruta)

    assert not (tmp_path / ruta).exists()


class ClienteS3Falso:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.puts: list[dict] = []
        self.deletes: list[dict] = []

    def put_object(self, **kwargs):
        if self.error:
            raise self.error
        self.puts.append(kwargs)

    def delete_object(self, **kwargs):
        if self.error:
            raise self.error
        self.deletes.append(kwargs)


async def test_s3_usa_sse_s3_y_la_ruta_relativa_como_clave():
    cliente = ClienteS3Falso()
    repo = S3AlmacenamientoFirmaRepository(bucket="bucket-privado", client=cliente)
    ruta = _ruta()

    await repo.guardar(ruta, ARCHIVO)

    assert cliente.puts == [
        {
            "Bucket": "bucket-privado",
            "Key": ruta,
            "Body": ARCHIVO.contenido,
            "ContentType": "image/png",
            "ServerSideEncryption": "AES256",
        }
    ]


async def test_s3_sin_bucket_configurado_falla():
    repo = S3AlmacenamientoFirmaRepository(bucket="", client=ClienteS3Falso())
    repo.bucket = ""

    with pytest.raises(AlmacenamientoFirmaError):
        await repo.guardar(_ruta(), ARCHIVO)


async def test_s3_traduce_errores_del_cliente():
    error = ClientError({"Error": {"Code": "AccessDenied", "Message": "no"}}, "PutObject")
    repo = S3AlmacenamientoFirmaRepository(bucket="b", client=ClienteS3Falso(error))

    with pytest.raises(AlmacenamientoFirmaError):
        await repo.guardar(_ruta(), ARCHIVO)


async def test_s3_eliminar_no_propaga_errores():
    error = ClientError({"Error": {"Code": "AccessDenied", "Message": "no"}}, "DeleteObject")
    repo = S3AlmacenamientoFirmaRepository(bucket="b", client=ClienteS3Falso(error))

    await repo.eliminar(_ruta())
