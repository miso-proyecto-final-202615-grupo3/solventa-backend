"""Cliente HTTP de MS Pólizas (HU1.3.8, tarea #265) para el reporte de siniestros (HU4.1.1).

Contrato real de MS Pólizas (rama `dev`, 12/11/2026):
- `GET {pólizas}/api/v1/insurancepolicies-service/polizas/mis-polizas` con `X-Client-Id` → lista de pólizas.
- `GET {pólizas}/api/v1/insurancepolicies-service/polizas/{poliza_id}` con `X-Client-Id` → la póliza,
  `404` si no existe o `403` si es de otro cliente.
Cada póliza trae `producto_id` (no el código). El código y el nombre del producto salen del catálogo del
Motor de Cotización (`GET {cotización}/api/v1/quotingengine-service/productos`), fuente de los productos,
con caché en memoria (el catálogo casi no cambia).
"""
import logging
import time
import uuid
from datetime import date, datetime

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from src.application.ports.polizas import PolizaResumen, PolizasNoDisponibles

logger = logging.getLogger(__name__)

PREFIJO_POLIZAS = "/api/v1/insurancepolicies-service/polizas"
RUTA_PRODUCTOS = "/api/v1/quotingengine-service/productos"


class _PolizaDto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    poliza_id: uuid.UUID
    cliente_id: uuid.UUID
    producto_id: uuid.UUID
    numero: str
    estado: str
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


class _ProductoDto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    producto_id: uuid.UUID
    codigo: str
    nombre: str


class HttpPolizasClient:
    def __init__(
        self,
        base_url: str,
        productos_url: str,
        timeout_seconds: float = 3.0,
        productos_ttl_seconds: int = 300,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._polizas = httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds, transport=transport)
        self._productos = httpx.AsyncClient(base_url=productos_url, timeout=timeout_seconds, transport=transport)
        self._productos_ttl = productos_ttl_seconds

    async def listar_por_cliente(self, cliente_id: uuid.UUID, correlation_id: str) -> list[PolizaResumen]:
        response = await self._get(self._polizas, f"{PREFIJO_POLIZAS}/mis-polizas", correlation_id, cliente_id)
        if response.status_code in (403, 404):
            return []
        try:
            dtos = [_PolizaDto.model_validate(item) for item in response.json()]
        except (ValueError, TypeError, ValidationError) as exc:
            raise PolizasNoDisponibles() from exc
        productos = await self._catalogo_productos(correlation_id)
        return [self._resumen(dto, productos) for dto in dtos]

    async def obtener(self, poliza_id: uuid.UUID, cliente_id: uuid.UUID, correlation_id: str) -> PolizaResumen | None:
        response = await self._get(self._polizas, f"{PREFIJO_POLIZAS}/{poliza_id}", correlation_id, cliente_id)
        if response.status_code in (403, 404):  # ajena o inexistente: el mismo 404 hacia la app
            return None
        try:
            dto = _PolizaDto.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise PolizasNoDisponibles() from exc
        return self._resumen(dto, await self._catalogo_productos(correlation_id))

    async def aclose(self) -> None:
        await self._polizas.aclose()
        await self._productos.aclose()

    @staticmethod
    def _resumen(dto: _PolizaDto, productos: dict[uuid.UUID, _ProductoDto]) -> PolizaResumen:
        producto = productos.get(dto.producto_id)
        return PolizaResumen(
            poliza_id=dto.poliza_id,
            cliente_id=dto.cliente_id,
            numero=dto.numero,
            estado=dto.estado,
            # Sin producto conocido no hay tipos de siniestro: la póliza no se ofrece en la app.
            producto_codigo=producto.codigo if producto else "",
            producto_nombre=producto.nombre if producto else "",
            vigencia_desde=dto.vigencia_desde,
            vigencia_hasta=dto.vigencia_hasta,
        )

    async def _catalogo_productos(self, correlation_id: str) -> dict[uuid.UUID, _ProductoDto]:
        guardado = _cache_productos.get(self._productos.base_url)
        if guardado and time.monotonic() - guardado[0] < self._productos_ttl:
            return guardado[1]
        response = await self._get(self._productos, RUTA_PRODUCTOS, correlation_id)
        try:
            productos = {p.producto_id: p for p in (_ProductoDto.model_validate(i) for i in response.json())}
        except (ValueError, TypeError, ValidationError) as exc:
            raise PolizasNoDisponibles() from exc
        _cache_productos[self._productos.base_url] = (time.monotonic(), productos)
        return productos

    @staticmethod
    async def _get(
        client: httpx.AsyncClient, path: str, correlation_id: str, cliente_id: uuid.UUID | None = None
    ) -> httpx.Response:
        headers = {"X-Correlation-Id": correlation_id}
        if cliente_id is not None:
            headers["X-Client-Id"] = str(cliente_id)
        try:
            response = await client.get(path, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("polizas_no_disponible error=%s correlation_id=%s", type(exc).__name__, correlation_id)
            raise PolizasNoDisponibles() from exc
        if response.status_code not in (403, 404) and not response.is_success:
            logger.warning("polizas_error status=%s correlation_id=%s", response.status_code, correlation_id)
            raise PolizasNoDisponibles()
        return response


_cache_productos: dict[object, tuple[float, dict[uuid.UUID, _ProductoDto]]] = {}


def limpiar_cache_productos() -> None:
    _cache_productos.clear()
