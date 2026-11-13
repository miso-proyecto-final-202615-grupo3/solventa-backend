"""Escritura y lectura de archivos privados bajo un directorio base local (solo desarrollo).

En POSIX cada directorio se abre sin seguir enlaces simbólicos y debe ser privado del proceso.
En Windows, que no ofrece esas garantías, se rechazan los enlaces simbólicos.
"""
import os
import stat
import uuid
from contextlib import ExitStack
from pathlib import Path, PurePosixPath


def _validar_ruta(ruta: PurePosixPath) -> None:
    if ruta.is_absolute() or ".." in ruta.parts or not ruta.name:
        raise OSError("Ruta de archivo no válida.")


def _abrir_directorio(base: Path, ruta: PurePosixPath, stack: ExitStack, crear: bool) -> int:
    directorio = os.open(base, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    stack.callback(os.close, directorio)
    for componente in ruta.parent.parts:
        if crear:
            try:
                os.mkdir(componente, mode=0o700, dir_fd=directorio)
            except FileExistsError:
                pass
        directorio = os.open(
            componente, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directorio
        )
        stack.callback(os.close, directorio)
        info = os.fstat(directorio)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise PermissionError("El directorio de archivos no es privado.")
    return directorio


def escribir_archivo_privado(
    base: Path, ruta: PurePosixPath, contenido: bytes, *, sobrescribir: bool
) -> None:
    _validar_ruta(ruta)
    if os.name == "nt":
        _escribir_windows(base, ruta, contenido, sobrescribir)
        return
    with ExitStack() as stack:
        directorio = _abrir_directorio(base, ruta, stack, crear=True)
        if not sobrescribir:
            fd = os.open(
                ruta.name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directorio,
            )
            with os.fdopen(fd, "wb") as destino:
                destino.write(contenido)
            return
        # Se escribe a un temporal y se renombra: quien lea nunca ve un archivo a medias.
        temporal = f".{ruta.name}.{uuid.uuid4().hex}.tmp"
        fd = os.open(
            temporal,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directorio,
        )
        try:
            with os.fdopen(fd, "wb") as destino:
                destino.write(contenido)
            os.replace(temporal, ruta.name, src_dir_fd=directorio, dst_dir_fd=directorio)
        except BaseException:
            try:
                os.unlink(temporal, dir_fd=directorio)
            except FileNotFoundError:
                pass
            raise


def leer_archivo_privado(base: Path, ruta: PurePosixPath) -> bytes:
    _validar_ruta(ruta)
    if os.name == "nt":
        return _leer_windows(base, ruta)
    with ExitStack() as stack:
        directorio = _abrir_directorio(base, ruta, stack, crear=False)
        fd = os.open(ruta.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directorio)
        with os.fdopen(fd, "rb") as origen:
            if not stat.S_ISREG(os.fstat(origen.fileno()).st_mode):
                raise OSError("El destino no es un archivo regular.")
            return origen.read()


def _directorio_base_windows(base: Path) -> None:
    if not base.exists() or base.is_symlink() or not base.is_dir():
        raise OSError("El directorio de archivos no es válido.")


def _escribir_windows(base: Path, ruta: PurePosixPath, contenido: bytes, sobrescribir: bool) -> None:
    _directorio_base_windows(base)
    directorio = base
    for componente in ruta.parent.parts:
        directorio /= componente
        if directorio.is_symlink():
            raise OSError("El directorio de archivos no puede ser un enlace simbólico.")
        directorio.mkdir(mode=0o700, exist_ok=True)
    destino = base / Path(ruta)
    if destino.is_symlink() or (destino.exists() and not sobrescribir):
        raise FileExistsError(destino)
    destino.write_bytes(contenido)


def _leer_windows(base: Path, ruta: PurePosixPath) -> bytes:
    _directorio_base_windows(base)
    destino = base
    for componente in ruta.parts:
        destino /= componente
        if destino.is_symlink():
            raise OSError("La ruta no puede incluir enlaces simbólicos.")
    return destino.read_bytes()
