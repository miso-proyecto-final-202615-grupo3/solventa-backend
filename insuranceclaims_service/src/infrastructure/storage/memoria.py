"""Almacén de evidencias en memoria, solo para pruebas (`ALMACEN_EVIDENCIAS=memoria`)."""
from datetime import UTC, datetime, timedelta

from src.application.ports.almacen_evidencias import AlmacenNoDisponible, CargaPrefirmada, MetadatosObjeto


class AlmacenEvidenciasEnMemoria:
    def __init__(self, reloj=lambda: datetime.now(UTC)) -> None:
        self.objetos: dict[str, tuple[bytes, str, str | None]] = {}
        self.cargas: dict[str, dict] = {}
        self.eliminados: list[str] = []
        self.caido = False
        self._reloj = reloj

    async def generar_carga(self, clave: str, content_type: str, tamano_max: int, ttl: timedelta) -> CargaPrefirmada:
        self._verificar()
        self.cargas[clave] = {"content_type": content_type, "tamano_max": tamano_max}
        return CargaPrefirmada(
            url="https://almacen.test/evidencias",
            campos={"key": clave, "Content-Type": content_type, "policy": "firmada"},
            expira_en=self._reloj() + ttl,
        )

    def simular_subida(self, clave: str, contenido: bytes, content_type: str, cifrado: str | None = "AES256") -> None:
        self.objetos[clave] = (contenido, content_type, cifrado)

    async def metadatos(self, clave: str) -> MetadatosObjeto | None:
        self._verificar()
        if clave not in self.objetos:
            return None
        contenido, content_type, cifrado = self.objetos[clave]
        return MetadatosObjeto(tamano=len(contenido), content_type=content_type, cifrado=cifrado)

    async def leer_inicio(self, clave: str, n_bytes: int) -> bytes:
        self._verificar()
        return self.objetos[clave][0][:n_bytes]

    async def eliminar(self, clave: str) -> None:
        self._verificar()
        self.objetos.pop(clave, None)
        self.eliminados.append(clave)

    async def aclose(self) -> None:
        return None

    def _verificar(self) -> None:
        if self.caido:
            raise AlmacenNoDisponible()
