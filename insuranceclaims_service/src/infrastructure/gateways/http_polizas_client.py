"""Cliente HTTP de MS Pólizas (dependencia DEP-1 del plan de HU4.1.1).

Contrato interno acordado con la tarea #265:
- `GET {base}/api/v1/insurancepolicies-service/polizas?cliente_id=<uuid>` → `{"polizas": [<poliza>]}`
- `GET {base}/api/v1/insurancepolicies-service/polizas/{poliza_id}` → `<poliza>` o `404`
con `<poliza>` = `{poliza_id, cliente_id, numero, estado, producto_codigo, producto_nombre, vigencia_desde, vigencia_hasta}`.
"""
import logging
import uuid
from datetime import date, datetime

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from src.application.ports.polizas import PolizaResumen, PolizasNoDisponibles

logger = logging.getLogger(__name__)

PREFIJO = "/api/v1/insurancepolicies-service/polizas"


class _PolizaDto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    poliza_id: uuid.UUID
    cliente_id: uuid.UUID
    numero: str
    estado: str
    producto_codigo: str
    producto_nombre: str
    vigencia_desde: date
    vigencia_hasta: date

    @field_validator("vigencia_desde", "vigencia_hasta", mode="before")
    @classmethod
    def _solo_fecha(cls, valor):
        # MS Pólizas guarda la vigencia como fecha y hora; aquí solo importa el día.
        if isinstance(valor, str) and "T" in valor:
            return datetime.fromisoformat(valor.replace("Z", "+00:00")).date()
        if isinstance(valor, datetime):
            return valor.date()
        return valor

    def a_resumen(self) -> PolizaResumen:
        return PolizaResumen(**self.model_dump())


class _ListaDto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    polizas: list[_PolizaDto]


class HttpPolizasClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 3.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds, transport=transport)

    async def listar_por_cliente(self, cliente_id: uuid.UUID, correlation_id: str) -> list[PolizaResumen]:
        response = await self._get(PREFIJO, correlation_id, params={"cliente_id": str(cliente_id)})
        if response.status_code == 404:
            return []
        return [dto.a_resumen() for dto in self._parse(response, _ListaDto).polizas]

    async def obtener(self, poliza_id: uuid.UUID, correlation_id: str) -> PolizaResumen | None:
        response = await self._get(f"{PREFIJO}/{poliza_id}", correlation_id)
        if response.status_code == 404:
            return None
        return self._parse(response, _PolizaDto).a_resumen()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, correlation_id: str, params: dict | None = None) -> httpx.Response:
        try:
            response = await self._client.get(path, params=params, headers={"X-Correlation-Id": correlation_id})
        except httpx.HTTPError as exc:
            logger.warning("polizas_no_disponible error=%s correlation_id=%s", type(exc).__name__, correlation_id)
            raise PolizasNoDisponibles() from exc
        if response.status_code != 404 and not response.is_success:
            logger.warning("polizas_error status=%s correlation_id=%s", response.status_code, correlation_id)
            raise PolizasNoDisponibles()
        return response

    @staticmethod
    def _parse(response: httpx.Response, modelo):
        try:
            return modelo.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise PolizasNoDisponibles() from exc
