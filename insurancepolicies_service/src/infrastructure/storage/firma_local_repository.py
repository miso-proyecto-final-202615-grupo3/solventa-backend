import logging
import os
import stat
from contextlib import ExitStack
from pathlib import Path, PurePosixPath

from starlette.concurrency import run_in_threadpool

from src.domain.firmas.entities import ArchivoFirma
from src.domain.firmas.repositories import (
    AlmacenamientoFirmaError,
    AlmacenamientoFirmaRepository,
)

logger = logging.getLogger(__name__)


class LocalAlmacenamientoFirmaRepository(AlmacenamientoFirmaRepository):
    """Guarda la firma bajo un directorio local (por defecto /tmp), solo para desarrollo."""

    def __init__(self, directorio_base: Path | str = "/tmp") -> None:
        self.directorio_base = Path(directorio_base)

    async def guardar(self, ruta: str, archivo: ArchivoFirma) -> None:
        try:
            await run_in_threadpool(self._guardar, PurePosixPath(ruta), archivo)
        except OSError as exc:
            logger.exception("No se pudo almacenar la firma localmente.")
            raise AlmacenamientoFirmaError("No se pudo almacenar la firma localmente.") from exc

    async def eliminar(self, ruta: str) -> None:
        try:
            await run_in_threadpool((self.directorio_base / ruta).unlink, True)
        except OSError:
            logger.warning("No se pudo eliminar la firma huérfana.", exc_info=True)

    def _guardar(self, ruta: PurePosixPath, archivo: ArchivoFirma) -> None:
        if ruta.is_absolute() or ".." in ruta.parts:
            raise OSError("Ruta de firma no válida.")
        if os.name == "nt":
            self._guardar_windows(ruta, archivo)
            return
        with ExitStack() as stack:
            directorio = os.open(
                self.directorio_base, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            )
            stack.callback(os.close, directorio)
            # Cada directorio se abre sin seguir enlaces y debe ser privado del proceso.
            for componente in ruta.parent.parts:
                try:
                    os.mkdir(componente, mode=0o700, dir_fd=directorio)
                except FileExistsError:
                    pass
                directorio = os.open(
                    componente,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=directorio,
                )
                stack.callback(os.close, directorio)
                info = os.fstat(directorio)
                if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
                    raise PermissionError("El directorio de firmas no es privado.")

            fd = os.open(
                ruta.name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directorio,
            )
            with os.fdopen(fd, "wb") as destino:
                destino.write(archivo.contenido)

    def _guardar_windows(self, ruta: PurePosixPath, archivo: ArchivoFirma) -> None:
        base = self.directorio_base
        if not base.exists() or base.is_symlink() or not base.is_dir():
            raise OSError("El directorio de firmas no es válido.")
        if os.name != "nt" and stat.S_IMODE(base.stat().st_mode) & 0o077:
            raise PermissionError("El directorio de firmas no es privado.")

        directorio = base
        for componente in ruta.parent.parts:
            directorio /= componente
            if directorio.is_symlink():
                raise OSError("El directorio de firmas no puede ser un enlace simbólico.")
            directorio.mkdir(mode=0o700, exist_ok=True)
            if os.name != "nt" and stat.S_IMODE(directorio.stat().st_mode) & 0o077:
                raise PermissionError("El directorio de firmas no es privado.")

        destino = base / Path(ruta)
        if destino.exists() or destino.is_symlink():
            raise FileExistsError(destino)
        destino.write_bytes(archivo.contenido)
        destino.chmod(0o600)
