from decimal import Decimal
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from src.application.ports.open_data_gateway import (
    OpenDataGateway,
    OpenDataNoDisponibleError,
)
from src.core.config import settings
from src.domain.open_data import CategoriaOpenData, PerfilTerritorial


class _OpenDataResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    categoria: CategoriaOpenData
    id_territorial: Decimal
    ir_publico: Decimal


class OpenDataHttpClient(OpenDataGateway):
    def __init__(self, client: httpx.AsyncClient, base_url: str | None = None):
        self._client = client
        self._base_url = (base_url or settings.OPEN_DATA_URL).rstrip("/")

    async def obtener_riesgo(self, ubicacion: dict[str, Any]) -> PerfilTerritorial:
        if not self._base_url:
            raise OpenDataNoDisponibleError
        try:
            response = await self._client.post(
                f"{self._base_url}/risk", json=ubicacion
            )
            response.raise_for_status()
            perfil = _OpenDataResponse.model_validate(response.json())
        except (httpx.HTTPError, ValueError, ValidationError) as exc:
            raise OpenDataNoDisponibleError from exc
        return PerfilTerritorial(categoria=perfil.categoria)
