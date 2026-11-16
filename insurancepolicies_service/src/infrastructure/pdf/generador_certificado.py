import base64
import io
import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from PIL import Image, ImageChops, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from src.application.ports.generador_pdf import GeneracionPdfError, GeneradorCertificadoPdf
from src.domain.certificados.entities import PLANTILLA_CERTIFICADO
from src.infrastructure.pdf.formatos import (
    formato_fecha,
    formato_moneda,
    formato_numero,
    formato_porcentaje,
)

logger = logging.getLogger(__name__)

DIRECTORIO_PLANTILLAS = Path(__file__).parent / "templates"
_TIPOS_IMAGEN = {"image/png", "image/jpeg"}


def _entorno(directorio: Path) -> Environment:
    entorno = Environment(
        loader=FileSystemLoader(directorio),
        autoescape=select_autoescape(["html"]),
        # Un dato faltante rompe la generación en vez de imprimir un certificado incompleto.
        undefined=StrictUndefined,
    )
    entorno.filters.update(
        fecha=formato_fecha,
        moneda=formato_moneda,
        numero=formato_numero,
        porcentaje=formato_porcentaje,
    )
    return entorno


class GeneradorCertificadoWeasyPrint(GeneradorCertificadoPdf):
    """Renderiza la plantilla HTML del certificado a un PDF de una sola página con WeasyPrint."""

    def __init__(
        self,
        plantilla: str = PLANTILLA_CERTIFICADO,
        directorio_plantillas: Path = DIRECTORIO_PLANTILLAS,
    ) -> None:
        self._plantilla = plantilla
        self._entorno = _entorno(directorio_plantillas)

    @property
    def plantilla(self) -> str:
        return self._plantilla

    async def generar(self, datos: dict[str, Any], firma: bytes, firma_content_type: str) -> bytes:
        # El render usa CPU: se saca del event loop para no frenar la API ni los consumidores.
        return await run_in_threadpool(self._generar, datos, firma, firma_content_type)

    def renderizar_html(self, datos: dict[str, Any], firma: bytes, firma_content_type: str) -> str:
        if firma_content_type not in _TIPOS_IMAGEN:
            raise GeneracionPdfError(f"Tipo de imagen de firma no soportado: {firma_content_type}.")
        self._validar_imagen(firma)
        imagen = base64.b64encode(firma).decode("ascii")
        try:
            return self._entorno.get_template(self._plantilla).render(
                **datos, firma_data_uri=f"data:{firma_content_type};base64,{imagen}"
            )
        except Exception as exc:
            raise GeneracionPdfError(f"No se pudo renderizar la plantilla: {exc}") from exc

    @staticmethod
    def _validar_imagen(firma: bytes) -> None:
        # WeasyPrint omite en silencio una imagen ilegible y tolera las truncadas: sin esto
        # podría salir un certificado con la firma ausente o en blanco.
        try:
            with Image.open(io.BytesIO(firma)) as imagen:
                imagen.load()
                rgba = imagen.convert("RGBA")
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
            raise GeneracionPdfError("La imagen de la firma no se puede leer.") from exc
        sobre_blanco = Image.alpha_composite(Image.new("RGBA", rgba.size, "white"), rgba).convert("RGB")
        if ImageChops.invert(sobre_blanco).getbbox() is None:
            raise GeneracionPdfError("La imagen de la firma está en blanco.")

    def _generar(self, datos: dict[str, Any], firma: bytes, firma_content_type: str) -> bytes:
        html = self.renderizar_html(datos, firma, firma_content_type)
        try:
            # Importación diferida: WeasyPrint necesita librerías nativas (Pango) que no hacen
            # falta para arrancar la API ni para los demás casos de uso.
            from weasyprint import HTML
            from weasyprint.urls import FatalURLFetchingError, URLFetcher
        except (ImportError, OSError) as exc:
            raise GeneracionPdfError(f"WeasyPrint no está disponible: {exc}") from exc
        try:
            # Solo URIs data:, la de la firma: la plantilla no puede leer archivos ni la red.
            documento = HTML(
                string=html, url_fetcher=URLFetcher(allowed_protocols=["data"], fail_on_errors=True)
            ).render()
        # FatalURLFetchingError hereda de BaseException, así que Exception no la captura.
        except (Exception, FatalURLFetchingError) as exc:
            raise GeneracionPdfError(f"No se pudo generar el PDF: {exc}") from exc
        if len(documento.pages) != 1:
            raise GeneracionPdfError(
                f"El certificado ocupa {len(documento.pages)} páginas y debe ocupar una."
            )
        return documento.write_pdf()
