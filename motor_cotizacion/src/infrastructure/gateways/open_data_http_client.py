from decimal import Decimal
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from src.application.ports.perfilamiento import (
    OpenDataNoDisponibleError,
    OpenDataProvider,
)
from src.core.config import settings
from src.domain.open_data import CategoriaOpenData, PerfilTerritorial


class OpenDataResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    categoria: CategoriaOpenData
    id_territorial: Decimal
    ir_publico: Decimal


class OpenDataHttpClient(OpenDataProvider):
    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str | None = None,
    ) -> None:
        self.client = client
        self.base_url = (base_url or settings.OPEN_DATA_URL).rstrip("/")

    async def obtener_riesgo_territorial(
        self, ubicacion: dict[str, Any]
    ) -> PerfilTerritorial:
        if not self.base_url:
            raise OpenDataNoDisponibleError
        try:
            response = await self.client.post(
                f"{self.base_url}/risk",
                json=ubicacion,
            )
            response.raise_for_status()
            perfil = OpenDataResponse.model_validate(response.json())
        except (httpx.HTTPError, ValueError, ValidationError) as exc:
            raise OpenDataNoDisponibleError from exc

        return PerfilTerritorial(
            categoria=perfil.categoria,
            id_territorial=perfil.id_territorial,
            ir_publico=perfil.ir_publico,
        )
