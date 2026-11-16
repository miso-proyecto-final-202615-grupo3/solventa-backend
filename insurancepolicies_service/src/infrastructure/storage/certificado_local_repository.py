import logging
from pathlib import Path, PurePosixPath

from starlette.concurrency import run_in_threadpool

from src.domain.certificados.repositories import (
    AlmacenamientoCertificadoError,
    AlmacenamientoCertificadoRepository,
    CertificadoNoEncontradoError,
)
from src.infrastructure.storage.archivos_locales import (
    escribir_archivo_privado,
    leer_archivo_privado,
)

logger = logging.getLogger(__name__)


class LocalAlmacenamientoCertificadoRepository(AlmacenamientoCertificadoRepository):
    """Guarda los certificados bajo un directorio local (por defecto /tmp), solo para desarrollo."""

    def __init__(self, directorio_base: Path | str = "/tmp") -> None:
        self.directorio_base = Path(directorio_base)

    async def guardar(self, ruta: str, contenido: bytes) -> None:
        try:
            await run_in_threadpool(
                escribir_archivo_privado,
                self.directorio_base,
                PurePosixPath(ruta),
                contenido,
                sobrescribir=True,
            )
        except OSError as exc:
            logger.exception("No se pudo almacenar el certificado localmente.")
            raise AlmacenamientoCertificadoError(
                "No se pudo almacenar el certificado localmente."
            ) from exc

    async def leer(self, ruta: str) -> bytes:
        try:
            return await run_in_threadpool(
                leer_archivo_privado, self.directorio_base, PurePosixPath(ruta)
            )
        except FileNotFoundError as exc:
            raise CertificadoNoEncontradoError(ruta) from exc
        except OSError as exc:
            logger.exception("No se pudo leer el certificado local.")
            raise AlmacenamientoCertificadoError("No se pudo leer el certificado localmente.") from exc

    async def eliminar(self, ruta: str) -> None:
        try:
            await run_in_threadpool((self.directorio_base / ruta).unlink, True)
        except OSError:
            logger.warning("No se pudo eliminar el certificado huérfano.", exc_info=True)
