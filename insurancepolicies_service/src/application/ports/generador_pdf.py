from abc import ABC, abstractmethod
from typing import Any


class GeneracionPdfError(Exception):
    pass


class GeneradorCertificadoPdf(ABC):
    @property
    @abstractmethod
    def plantilla(self) -> str:
        """Nombre de la plantilla con la que se genera el PDF."""
        raise NotImplementedError

    @abstractmethod
    async def generar(self, datos: dict[str, Any], firma: bytes, firma_content_type: str) -> bytes:
        """Renderiza el certificado de una sola página; la firma solo se incrusta, no va en datos."""
        raise NotImplementedError
