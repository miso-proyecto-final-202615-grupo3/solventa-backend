import uuid
from datetime import UTC, datetime

import pytest

from src.application.use_cases.capturar_firma_digital_use_case import (
    CapturarFirmaDigitalUseCase,
    FirmaConcurrenteError,
    FirmaYaVinculadaError,
)
from src.domain.firmas.entities import ArchivoFirma, EstadoFirma, FirmaDigital
from src.domain.firmas.repositories import (
    AlmacenamientoFirmaRepository,
    FirmaDigitalRepository,
    FirmaDuplicadaError,
)

ARCHIVO = ArchivoFirma(b"\x89PNG\r\n\x1a\n" + b"firma", "image/png")


def _firma(cliente_id, cotizacion_id, producto_id, clave="k1", estado=EstadoFirma.CAPTURADA):
    return FirmaDigital(
        cliente_id=cliente_id,
        cotizacion_id=cotizacion_id,
        producto_id=producto_id,
        proveedor_firma="CANVAS_MANUSCRITA",
        ruta_imagen="firma-digital/x/y/firma.png",
        content_type="image/png",
        tamano_bytes=1,
        firma_hash=ARCHIVO.hash,
        fingerprint_contrato="f" * 64,
        capturada_en=datetime.now(UTC),
        idempotency_key=clave,
        correlation_id="c",
        estado=estado,
    )


class RepoFalso(FirmaDigitalRepository):
    def __init__(self, activa=None, ganadora=None):
        self.activa = activa
        # firma que "otro request" inserta justo antes de nuestro crear()
        self.ganadora = ganadora
        self.por_clave = {}

    async def crear(self, firma):
        if self.ganadora is not None:
            self.por_clave[(self.ganadora.cliente_id, self.ganadora.idempotency_key)] = (
                self.ganadora
            )
            raise FirmaDuplicadaError()

    async def obtener_por_idempotency_key(self, cliente_id, idempotency_key):
        return self.por_clave.get((cliente_id, idempotency_key))

    async def obtener_activa_por_cotizacion(self, cotizacion_id):
        return self.activa

    async def reemplazar_capturada(self, cotizacion_id):
        pass


class AlmacenamientoFalso(AlmacenamientoFirmaRepository):
    def __init__(self):
        self.guardadas: list[str] = []
        self.eliminadas: list[str] = []

    async def guardar(self, ruta, archivo):
        self.guardadas.append(ruta)

    async def eliminar(self, ruta):
        self.eliminadas.append(ruta)


class Transaccion:
    def __init__(self, falla_commit=False):
        self.falla_commit = falla_commit
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        if self.falla_commit:
            raise RuntimeError("commit falló")
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _caso(repo, almacenamiento, tx):
    return CapturarFirmaDigitalUseCase(
        repo, almacenamiento, tx.commit, tx.rollback, 1024, "CANVAS_MANUSCRITA"
    )


async def test_carrera_con_la_misma_clave_devuelve_la_firma_ganadora():
    cliente, cotizacion, producto = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    repo = RepoFalso(ganadora=_firma(cliente, cotizacion, producto))
    almacenamiento, tx = AlmacenamientoFalso(), Transaccion()

    resultado = await _caso(repo, almacenamiento, tx).ejecutar(
        cliente, cotizacion, producto, ARCHIVO, "k1", "c"
    )

    assert resultado.creada is False
    assert resultado.firma is repo.ganadora
    assert tx.rollbacks == 1 and tx.commits == 0
    assert almacenamiento.guardadas == []


async def test_carrera_con_otra_clave_es_conflicto():
    cliente, cotizacion, producto = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    repo = RepoFalso(ganadora=_firma(cliente, cotizacion, producto, clave="otra"))
    almacenamiento, tx = AlmacenamientoFalso(), Transaccion()

    with pytest.raises(FirmaConcurrenteError):
        await _caso(repo, almacenamiento, tx).ejecutar(
            cliente, cotizacion, producto, ARCHIVO, "k1", "c"
        )

    assert tx.rollbacks == 1
    assert almacenamiento.guardadas == []


async def test_firma_vinculada_a_poliza_no_se_reemplaza():
    cliente, cotizacion, producto = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    repo = RepoFalso(activa=_firma(cliente, cotizacion, producto, estado=EstadoFirma.VINCULADA))

    with pytest.raises(FirmaYaVinculadaError):
        await _caso(repo, AlmacenamientoFalso(), Transaccion()).ejecutar(
            cliente, cotizacion, producto, ARCHIVO, "k2", "c"
        )


async def test_si_falla_el_commit_se_elimina_el_archivo_subido():
    cliente, cotizacion, producto = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    almacenamiento, tx = AlmacenamientoFalso(), Transaccion(falla_commit=True)

    with pytest.raises(RuntimeError):
        await _caso(RepoFalso(), almacenamiento, tx).ejecutar(
            cliente, cotizacion, producto, ARCHIVO, "k1", "c"
        )

    assert tx.rollbacks == 1
    assert almacenamiento.eliminadas == almacenamiento.guardadas != []
