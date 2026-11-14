"""Reglas puras de evidencias (HU4.1.2, decisión E6). Las cantidades salen de la tabla `tipo_siniestro`."""
from dataclasses import dataclass
from datetime import timedelta

from src.domain.siniestros.catalogo import ReglasEvidencia
from src.domain.siniestros.entities import Siniestro
from src.domain.siniestros.enums import EstadoSiniestro
from src.domain.siniestros.errores import (
    EvidenciaDemasiadoGrande,
    FormatoNoSoportado,
    LimiteEvidencias,
    SiniestroNoAdmiteEvidencias,
    TipoEvidenciaNoPermitido,
)
from src.domain.siniestros.evidencias import TipoEvidencia

MB = 1024 * 1024


@dataclass(frozen=True)
class LimitesEvidencia:
    foto_max_bytes: int = 5 * MB
    video_max_bytes: int = 50 * MB
    ttl_foto: timedelta = timedelta(minutes=10)
    ttl_video: timedelta = timedelta(minutes=30)


class PoliticaEvidencias:
    CONTENT_TYPES = {TipoEvidencia.FOTO: "image/jpeg", TipoEvidencia.VIDEO: "video/mp4"}

    def __init__(self, limites: LimitesEvidencia | None = None) -> None:
        self.limites = limites or LimitesEvidencia()

    def validar_estado(self, siniestro: Siniestro) -> None:
        if siniestro.estado != EstadoSiniestro.REPORTADO.value:
            raise SiniestroNoAdmiteEvidencias()

    def validar_solicitud(
        self,
        siniestro: Siniestro,
        reglas: ReglasEvidencia,
        tipo: TipoEvidencia,
        content_type: str,
        tamano: int,
        vigentes_del_tipo: int,
    ) -> None:
        """Orden: estado del siniestro → tipo admitido → formato → tamaño → cantidad."""
        self.validar_estado(siniestro)
        maximo = reglas.fotos_max if tipo == TipoEvidencia.FOTO else reglas.videos_max
        if maximo == 0:
            raise TipoEvidenciaNoPermitido()
        if content_type.lower() != self.CONTENT_TYPES[tipo]:
            raise FormatoNoSoportado()
        if tamano > self.max_bytes(tipo):
            raise EvidenciaDemasiadoGrande()
        if vigentes_del_tipo >= maximo:
            raise LimiteEvidencias()

    def max_bytes(self, tipo: TipoEvidencia) -> int:
        return self.limites.foto_max_bytes if tipo == TipoEvidencia.FOTO else self.limites.video_max_bytes

    def ttl(self, tipo: TipoEvidencia) -> timedelta:
        return self.limites.ttl_foto if tipo == TipoEvidencia.FOTO else self.limites.ttl_video

    @staticmethod
    def firma_valida(tipo: TipoEvidencia, primeros_bytes: bytes) -> bool:
        """JPEG empieza con FF D8 FF; MP4 tiene `ftyp` en los bytes 4 a 7."""
        if tipo == TipoEvidencia.FOTO:
            return primeros_bytes[:3] == b"\xff\xd8\xff"
        return primeros_bytes[4:8] == b"ftyp"
