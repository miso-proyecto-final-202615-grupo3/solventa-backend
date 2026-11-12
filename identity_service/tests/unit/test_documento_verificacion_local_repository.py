import stat
import uuid
import os
from pathlib import Path

import pytest

from src.domain.verificaciones_kyc_aml.entities import ArchivoDocumento
from src.domain.verificaciones_kyc_aml.repositories import AlmacenamientoDocumentosError
from src.infrastructure.storage.documento_verificacion_local_repository import (
    LocalDocumentoVerificacionRepository,
)

JPEG = ArchivoDocumento(b"\xff\xd8\xff-frontal", "image/jpeg")
PNG = ArchivoDocumento(b"\x89PNG\r\n\x1a\n-reverso", "image/png")


def test_directorio_predeterminado_es_tmp():
    assert LocalDocumentoVerificacionRepository().directorio_base == Path("/tmp")


async def test_guarda_documentos_con_rutas_y_permisos_privados(tmp_path):
    repo = LocalDocumentoVerificacionRepository(tmp_path)
    cliente_id, verificacion_id = uuid.uuid4(), uuid.uuid4()

    rutas = await repo.guardar(cliente_id, verificacion_id, JPEG, PNG)

    base = tmp_path / "verificaciones-kyc-aml" / str(cliente_id) / str(verificacion_id)
    frontal = base / "documento-frontal.jpg"
    reverso = base / "documento-reverso.png"
    assert rutas.frontal == str(frontal)
    assert rutas.reverso == str(reverso)
    assert frontal.read_bytes() == JPEG.contenido
    assert reverso.read_bytes() == PNG.contenido
    if os.name != "nt":
        for directorio in (base, base.parent, base.parent.parent):
            assert stat.S_IMODE(directorio.stat().st_mode) == 0o700
        assert stat.S_IMODE(frontal.stat().st_mode) == 0o600
        assert stat.S_IMODE(reverso.stat().st_mode) == 0o600


async def test_reintento_sobrescribe_los_mismos_archivos(tmp_path):
    repo = LocalDocumentoVerificacionRepository(tmp_path)
    cliente_id, verificacion_id = uuid.uuid4(), uuid.uuid4()
    primera = await repo.guardar(cliente_id, verificacion_id, JPEG, PNG)
    nuevo_frontal = ArchivoDocumento(b"\xff\xd8\xff-x", "image/jpeg")

    segunda = await repo.guardar(cliente_id, verificacion_id, nuevo_frontal, PNG)

    assert primera == segunda
    assert Path(segunda.frontal).read_bytes() == nuevo_frontal.contenido
    assert Path(segunda.reverso).read_bytes() == PNG.contenido


async def test_los_intentos_se_almacenan_por_separado(tmp_path):
    repo = LocalDocumentoVerificacionRepository(tmp_path)
    cliente_id = uuid.uuid4()
    primera = await repo.guardar(cliente_id, uuid.uuid4(), JPEG, PNG)
    segunda = await repo.guardar(cliente_id, uuid.uuid4(), JPEG, PNG)

    assert primera.frontal != segunda.frontal
    assert Path(primera.frontal).read_bytes() == JPEG.contenido
    assert Path(segunda.frontal).read_bytes() == JPEG.contenido


async def test_error_de_almacenamiento_se_traduce(tmp_path):
    repo = LocalDocumentoVerificacionRepository(tmp_path / "no-existe")

    with pytest.raises(AlmacenamientoDocumentosError):
        await repo.guardar(uuid.uuid4(), uuid.uuid4(), JPEG, PNG)


async def test_rechaza_directorio_que_no_es_privado(tmp_path):
    if os.name == "nt":
        pytest.skip("Windows administra permisos mediante ACL, no bits POSIX.")
    base = tmp_path / "verificaciones-kyc-aml"
    base.mkdir(mode=0o755)
    base.chmod(0o755)

    with pytest.raises(AlmacenamientoDocumentosError):
        await LocalDocumentoVerificacionRepository(tmp_path).guardar(
            uuid.uuid4(), uuid.uuid4(), JPEG, PNG
        )


async def test_rechaza_directorio_simbolico(tmp_path):
    if os.name == "nt":
        pytest.skip("Windows requiere privilegios para crear enlaces simbólicos.")
    destino = tmp_path / "destino"
    destino.mkdir()
    (tmp_path / "verificaciones-kyc-aml").symlink_to(destino, target_is_directory=True)

    with pytest.raises(AlmacenamientoDocumentosError):
        await LocalDocumentoVerificacionRepository(tmp_path).guardar(
            uuid.uuid4(), uuid.uuid4(), JPEG, PNG
        )

    assert list(destino.iterdir()) == []


async def test_rechaza_archivo_simbolico_en_reintento(tmp_path):
    if os.name == "nt":
        pytest.skip("Windows requiere privilegios para crear enlaces simbólicos.")
    repo = LocalDocumentoVerificacionRepository(tmp_path)
    cliente_id, verificacion_id = uuid.uuid4(), uuid.uuid4()
    rutas = await repo.guardar(cliente_id, verificacion_id, JPEG, PNG)
    objetivo = tmp_path / "otro-archivo"
    objetivo.write_bytes(b"sin cambios")
    Path(rutas.frontal).unlink()
    Path(rutas.frontal).symlink_to(objetivo)

    with pytest.raises(AlmacenamientoDocumentosError):
        await repo.guardar(cliente_id, verificacion_id, JPEG, PNG)

    assert objetivo.read_bytes() == b"sin cambios"
