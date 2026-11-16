import logging
import uuid

import httpx

from src.application.ports.kyc_aml import KycAmlProvider, ProveedorKycAmlError
from src.core.config import settings
from src.domain.verificaciones_kyc_aml.entities import (
    ArchivoDocumento,
    InicioProveedor,
    ResultadoChequeo,
    ResultadoProveedor,
    RutasDocumentos,
)

logger = logging.getLogger(__name__)

_RESULTADOS = {
    "PASSED": ResultadoChequeo.APROBADO,
    "FAILED": ResultadoChequeo.RECHAZADO,
    "PENDING": ResultadoChequeo.PENDIENTE,
}
_PATH = "/verificaciones-kyc-aml"


class KycAmlHttpClient(KycAmlProvider):
    """Consume el proveedor (o mock) de validaciones KYC y AML."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.nombre = settings.KYC_PROVIDER_NAME
        self._client = httpx.AsyncClient(
            base_url=base_url or settings.KYC_SERVICE_URL,
            timeout=timeout or settings.KYC_TIMEOUT_SECONDS,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def iniciar_verificacion(
        self,
        cliente_id: uuid.UUID,
        verificacion_id: uuid.UUID,
        rutas: RutasDocumentos,
        frontal: ArchivoDocumento,
        reverso: ArchivoDocumento,
        correlation_id: str,
    ) -> InicioProveedor:
        cuerpo = await self._solicitar(
            "POST",
            _PATH,
            correlation_id,
            data={
                "cliente_id": str(cliente_id),
                "verificacion_id": str(verificacion_id),
                "ruta_documento_frontal": rutas.frontal,
                "ruta_documento_reverso": rutas.reverso,
            },
            files={
                "documento_frontal": (
                    f"frontal.{frontal.extension}", frontal.contenido, frontal.content_type
                ),
                "documento_reverso": (
                    f"reverso.{reverso.extension}", reverso.contenido, reverso.content_type
                ),
            },
        )
        externo = cuerpo.get("verification_id")
        if not externo:
            raise ProveedorKycAmlError(
                "RESPUESTA_INVALIDA", "El proveedor no devolvió el identificador de verificación."
            )
        return InicioProveedor(verificacion_externa_id=str(externo), respuesta=cuerpo)

    async def consultar_resultado(
        self, verificacion_externa_id: str, correlation_id: str
    ) -> ResultadoProveedor:
        cuerpo = await self._solicitar(
            "GET", f"{_PATH}/{verificacion_externa_id}", correlation_id
        )
        return ResultadoProveedor(
            kyc=_RESULTADOS.get(str(cuerpo.get("kyc_status")), ResultadoChequeo.PENDIENTE),
            aml=_RESULTADOS.get(str(cuerpo.get("aml_status")), ResultadoChequeo.PENDIENTE),
            respuesta=cuerpo,
        )

    async def _solicitar(self, metodo: str, ruta: str, correlation_id: str, **kwargs) -> dict:
        try:
            response = await self._client.request(
                metodo, ruta, headers={"X-Correlation-Id": correlation_id}, **kwargs
            )
        except httpx.HTTPError as exc:
            raise ProveedorKycAmlError(
                "PROVEEDOR_NO_DISPONIBLE", f"{type(exc).__name__} al consultar el proveedor."
            ) from exc
        if response.status_code >= 400:
            raise ProveedorKycAmlError(
                f"PROVEEDOR_HTTP_{response.status_code}",
                "El proveedor respondió con un error.",
            )
        try:
            cuerpo = response.json()
        except ValueError as exc:
            raise ProveedorKycAmlError(
                "RESPUESTA_INVALIDA", "El proveedor devolvió una respuesta no válida."
            ) from exc
        if not isinstance(cuerpo, dict):
            raise ProveedorKycAmlError(
                "RESPUESTA_INVALIDA", "El proveedor devolvió una respuesta no válida."
            )
        return cuerpo
