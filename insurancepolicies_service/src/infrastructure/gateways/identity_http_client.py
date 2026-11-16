import uuid

import httpx

from src.application.ports.servicios import ServicioNoDisponibleError
from src.application.ports.titulares import Titular, TitularGateway
from src.core.config import settings
from src.infrastructure.gateways.http_utils import solicitar_json

_SERVICIO = "identity_service"


class IdentityHttpClient(TitularGateway):
    """Consulta en Identidad el nombre y el documento del titular de la póliza."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url or settings.IDENTITY_SERVICE_URL,
            timeout=timeout or settings.SERVICES_TIMEOUT_SECONDS,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def obtener(self, cliente_id: uuid.UUID, correlation_id: str) -> Titular:
        cuerpo = await solicitar_json(
            self._client,
            _SERVICIO,
            f"/api/v1/identity-service/clientes/{cliente_id}/perfil",
            correlation_id,
        )
        try:
            return Titular(
                nombre_completo=f"{cuerpo['nombres']} {cuerpo['apellidos']}".strip(),
                tipo_documento=str(cuerpo["tipo_documento"]),
                numero_identificacion=str(cuerpo["numero_identificacion"]),
            )
        except (KeyError, TypeError) as exc:
            raise ServicioNoDisponibleError(_SERVICIO, "perfil inválido") from exc
