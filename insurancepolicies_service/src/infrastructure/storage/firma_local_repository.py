import logging
from pathlib import Path, PurePosixPath

from starlette.concurrency import run_in_threadpool

from src.domain.firmas.entities import ArchivoFirma
from src.domain.firmas.repositories import (
    AlmacenamientoFirmaError,
    AlmacenamientoFirmaRepository,
)
from src.infrastructure.storage.archivos_locales import (
    escribir_archivo_privado,
    leer_archivo_privado,
)

logger = logging.getLogger(__name__)


class LocalAlmacenamientoFirmaRepository(AlmacenamientoFirmaRepository):
    """Guarda la firma bajo un directorio local (por defecto /tmp), solo para desarrollo."""

    def __init__(self, directorio_base: Path | str = "/tmp") -> None:
        self.directorio_base = Path(directorio_base)

    async def guardar(self, ruta: str, archivo: ArchivoFirma) -> None:
        try:
            await run_in_threadpool(
                escribir_archivo_privado,
                self.directorio_base,
                PurePosixPath(ruta),
                archivo.contenido,
                sobrescribir=False,
            )
        except OSError as exc:
            logger.exception("No se pudo almacenar la firma localmente.")
            raise AlmacenamientoFirmaError("No se pudo almacenar la firma localmente.") from exc

    async def leer(self, ruta: str) -> bytes:
        try:
            return await run_in_threadpool(
                leer_archivo_privado, self.directorio_base, PurePosixPath(ruta)
            )
        except OSError as exc:
            logger.exception("No se pudo leer la firma local.")
            raise AlmacenamientoFirmaError("No se pudo leer la firma localmente.") from exc

    async def eliminar(self, ruta: str) -> None:
        try:
            await run_in_threadpool((self.directorio_base / ruta).unlink, True)
        except OSError:
            logger.warning("No se pudo eliminar la firma huérfana.", exc_info=True)
