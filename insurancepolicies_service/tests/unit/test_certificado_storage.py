import os
import stat
import uuid

import pytest
from botocore.exceptions import ClientError

from src.domain.certificados.entities import construir_ruta_certificado
from src.domain.certificados.repositories import (
    AlmacenamientoCertificadoError,
    CertificadoNoEncontradoError,
)
from src.domain.firmas.entities import ArchivoFirma, construir_ruta
from src.domain.firmas.repositories import AlmacenamientoFirmaError
from src.infrastructure.storage.certificado_local_repository import (
    LocalAlmacenamientoCertificadoRepository,
)
from src.infrastructure.storage.certificado_s3_repository import S3AlmacenamientoCertificadoRepository
from src.infrastructure.storage.firma_local_repository import LocalAlmacenamientoFirmaRepository
from src.infrastructure.storage.firma_s3_repository import S3AlmacenamientoFirmaRepository

PDF = b"%PDF-1.7 contenido de prueba"


def ruta() -> str:
    return construir_ruta_certificado(uuid.uuid4(), uuid.uuid4())


def test_ruta_del_certificado_es_relativa_por_cliente_y_poliza():
    cliente, poliza = uuid.uuid4(), uuid.uuid4()

    assert construir_ruta_certificado(cliente, poliza) == (
        f"certificados-poliza/{cliente}/{poliza}/certificado-poliza.pdf"
    )


async def test_local_guarda_y_lee_con_permisos_privados(tmp_path):
    repo = LocalAlmacenamientoCertificadoRepository(tmp_path)
    r = ruta()

    await repo.guardar(r, PDF)

    assert await repo.leer(r) == PDF
    destino = tmp_path / r
    assert destino.read_bytes() == PDF
    if os.name != "nt":
        assert stat.S_IMODE(destino.stat().st_mode) == 0o600
        assert stat.S_IMODE(destino.parent.stat().st_mode) == 0o700


async def test_local_reemplaza_el_certificado_existente_sin_dejar_temporales(tmp_path):
    repo = LocalAlmacenamientoCertificadoRepository(tmp_path)
    r = ruta()
    await repo.guardar(r, PDF)

    await repo.guardar(r, PDF + b" nueva version")

    assert await repo.leer(r) == PDF + b" nueva version"
    assert [p.name for p in (tmp_path / r).parent.iterdir()] == ["certificado-poliza.pdf"]


async def test_local_leer_inexistente(tmp_path):
    with pytest.raises(CertificadoNoEncontradoError):
        await LocalAlmacenamientoCertificadoRepository(tmp_path).leer(ruta())


@pytest.mark.parametrize("peligrosa", ["../fuera/certificado.pdf", "/abs/certificado.pdf", "a/../../b.pdf"])
async def test_local_rechaza_rutas_fuera_del_directorio(tmp_path, peligrosa):
    repo = LocalAlmacenamientoCertificadoRepository(tmp_path)

    with pytest.raises(AlmacenamientoCertificadoError):
        await repo.guardar(peligrosa, PDF)
    with pytest.raises(AlmacenamientoCertificadoError):
        await repo.leer(peligrosa)


async def test_local_no_sigue_enlaces_simbolicos(tmp_path):
    if os.name == "nt":
        pytest.skip("Windows requiere privilegios para crear enlaces simbólicos.")
    base = tmp_path / "base"
    base.mkdir()
    fuera = tmp_path / "fuera"
    fuera.mkdir()
    (fuera / "secreto.pdf").write_bytes(b"secreto")
    os.symlink(fuera, base / "certificados-poliza")
    repo = LocalAlmacenamientoCertificadoRepository(base)

    with pytest.raises(AlmacenamientoCertificadoError):
        await repo.guardar(ruta(), PDF)
    with pytest.raises(AlmacenamientoCertificadoError):
        await repo.leer("certificados-poliza/secreto.pdf")
    assert [p.name for p in fuera.iterdir()] == ["secreto.pdf"]


async def test_local_no_sigue_un_enlace_simbolico_como_archivo(tmp_path):
    if os.name == "nt":
        pytest.skip("Windows requiere privilegios para crear enlaces simbólicos.")
    repo = LocalAlmacenamientoCertificadoRepository(tmp_path)
    r = ruta()
    await repo.guardar(r, PDF)
    secreto = tmp_path / "secreto.txt"
    secreto.write_bytes(b"secreto")
    destino = tmp_path / r
    destino.unlink()
    os.symlink(secreto, destino)

    with pytest.raises(AlmacenamientoCertificadoError):
        await repo.leer(r)
    await repo.guardar(r, PDF)  # reemplaza el enlace, no escribe a través de él

    assert secreto.read_bytes() == b"secreto" and await repo.leer(r) == PDF


async def test_local_directorio_no_privado_se_rechaza(tmp_path):
    if os.name == "nt":
        pytest.skip("Los permisos POSIX no aplican en Windows.")
    repo = LocalAlmacenamientoCertificadoRepository(tmp_path)
    r = ruta()
    await repo.guardar(r, PDF)
    (tmp_path / r).parent.chmod(0o755)

    with pytest.raises(AlmacenamientoCertificadoError):
        await repo.leer(r)


async def test_local_elimina_y_tolera_inexistente(tmp_path):
    repo = LocalAlmacenamientoCertificadoRepository(tmp_path)
    r = ruta()
    await repo.guardar(r, PDF)

    await repo.eliminar(r)
    await repo.eliminar(r)

    assert not (tmp_path / r).exists()


async def test_firma_local_ahora_tambien_se_puede_leer(tmp_path):
    repo = LocalAlmacenamientoFirmaRepository(tmp_path)
    r = construir_ruta(uuid.uuid4(), uuid.uuid4(), "firma.png")
    contenido = b"\x89PNG\r\n\x1a\nfirma"
    await repo.guardar(r, ArchivoFirma(contenido, "image/png"))

    assert await repo.leer(r) == contenido
    with pytest.raises(AlmacenamientoFirmaError):
        await repo.leer(construir_ruta(uuid.uuid4(), uuid.uuid4(), "firma.png"))


class Cuerpo:
    def __init__(self, contenido: bytes) -> None:
        self.contenido = contenido

    def read(self) -> bytes:
        return self.contenido


class ClienteS3Falso:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.objetos: dict[str, bytes] = {}
        self.puts: list[dict] = []
        self.deletes: list[dict] = []

    def put_object(self, **kwargs):
        if self.error:
            raise self.error
        self.puts.append(kwargs)
        self.objetos[kwargs["Key"]] = kwargs["Body"]

    def get_object(self, **kwargs):
        if self.error:
            raise self.error
        if kwargs["Key"] not in self.objetos:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "x"}}, "GetObject")
        return {"Body": Cuerpo(self.objetos[kwargs["Key"]])}

    def delete_object(self, **kwargs):
        if self.error:
            raise self.error
        self.deletes.append(kwargs)


def error_s3(codigo: str, operacion: str) -> ClientError:
    return ClientError({"Error": {"Code": codigo, "Message": "x"}}, operacion)


async def test_s3_guarda_en_bucket_privado_con_sse_s3_y_la_ruta_relativa_como_clave():
    cliente = ClienteS3Falso()
    repo = S3AlmacenamientoCertificadoRepository(bucket="bucket-privado", client=cliente)
    r = ruta()

    await repo.guardar(r, PDF)

    assert cliente.puts == [
        {
            "Bucket": "bucket-privado",
            "Key": r,
            "Body": PDF,
            "ContentType": "application/pdf",
            "ServerSideEncryption": "AES256",
        }
    ]
    assert "SSEKMSKeyId" not in cliente.puts[0]
    assert await repo.leer(r) == PDF


async def test_s3_leer_inexistente():
    repo = S3AlmacenamientoCertificadoRepository(bucket="b", client=ClienteS3Falso())

    with pytest.raises(CertificadoNoEncontradoError):
        await repo.leer(ruta())


async def test_s3_traduce_otros_errores_del_cliente():
    repo = S3AlmacenamientoCertificadoRepository(
        bucket="b", client=ClienteS3Falso(error_s3("AccessDenied", "GetObject"))
    )

    with pytest.raises(AlmacenamientoCertificadoError) as exc:
        await repo.leer(ruta())
    assert not isinstance(exc.value, CertificadoNoEncontradoError)
    with pytest.raises(AlmacenamientoCertificadoError):
        await repo.guardar(ruta(), PDF)


async def test_s3_sin_bucket_configurado_falla():
    repo = S3AlmacenamientoCertificadoRepository(bucket="", client=ClienteS3Falso())
    repo.bucket = ""

    with pytest.raises(AlmacenamientoCertificadoError):
        await repo.guardar(ruta(), PDF)
    with pytest.raises(AlmacenamientoCertificadoError):
        await repo.leer(ruta())


async def test_s3_eliminar_no_propaga_errores():
    repo = S3AlmacenamientoCertificadoRepository(
        bucket="b", client=ClienteS3Falso(error_s3("AccessDenied", "DeleteObject"))
    )

    await repo.eliminar(ruta())


async def test_firma_s3_ahora_tambien_se_puede_leer():
    cliente = ClienteS3Falso()
    repo = S3AlmacenamientoFirmaRepository(bucket="b", client=cliente)
    r = construir_ruta(uuid.uuid4(), uuid.uuid4(), "firma.png")
    cliente.objetos[r] = b"imagen"

    assert await repo.leer(r) == b"imagen"
    with pytest.raises(AlmacenamientoFirmaError):
        await repo.leer("no/existe.png")
