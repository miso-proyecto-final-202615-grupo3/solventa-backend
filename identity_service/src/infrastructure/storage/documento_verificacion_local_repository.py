import logging
import os
import stat
import uuid
from contextlib import ExitStack
from pathlib import Path

from starlette.concurrency import run_in_threadpool

from src.domain.verificaciones_kyc_aml.entities import (
    ArchivoDocumento,
    RutasDocumentos,
    construir_ruta,
)
from src.domain.verificaciones_kyc_aml.repositories import (
    AlmacenamientoDocumentosError,
    DocumentoVerificacionRepository,
)

logger = logging.getLogger(__name__)


class LocalDocumentoVerificacionRepository(DocumentoVerificacionRepository):
    def __init__(self, directorio_base: Path = Path("/tmp")) -> None:
        self.directorio_base = directorio_base

    async def guardar(
        self,
        cliente_id: uuid.UUID,
        verificacion_id: uuid.UUID,
        frontal: ArchivoDocumento,
        reverso: ArchivoDocumento,
    ) -> RutasDocumentos:
        try:
            return await run_in_threadpool(
                self._guardar, cliente_id, verificacion_id, frontal, reverso
            )
        except OSError as exc:
            logger.exception("No se pudieron almacenar los documentos localmente.")
            raise AlmacenamientoDocumentosError(
                "No se pudieron almacenar los documentos localmente."
            ) from exc

    def _guardar(
        self,
        cliente_id: uuid.UUID,
        verificacion_id: uuid.UUID,
        frontal: ArchivoDocumento,
        reverso: ArchivoDocumento,
    ) -> RutasDocumentos:
        rutas = [
            Path(
                construir_ruta(
                    cliente_id, verificacion_id, f"documento-{lado}.{archivo.extension}"
                )
            )
            for lado, archivo in (("frontal", frontal), ("reverso", reverso))
        ]
        with ExitStack() as stack:
            directorio = os.open(
                self.directorio_base, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            )
            stack.callback(os.close, directorio)
            for componente in rutas[0].parent.parts:
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
                    raise PermissionError("El directorio de documentos no es privado.")

            for ruta, archivo in zip(rutas, (frontal, reverso)):
                fd = os.open(
                    ruta.name,
                    os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                    0o600,
                    dir_fd=directorio,
                )
                with os.fdopen(fd, "wb") as destino:
                    if not stat.S_ISREG(os.fstat(destino.fileno()).st_mode):
                        raise OSError("El destino de documentos no es un archivo regular.")
                    os.fchmod(destino.fileno(), 0o600)
                    os.ftruncate(destino.fileno(), 0)
                    destino.write(archivo.contenido)

        return RutasDocumentos(
            frontal=str(self.directorio_base / rutas[0]),
            reverso=str(self.directorio_base / rutas[1]),
        )
