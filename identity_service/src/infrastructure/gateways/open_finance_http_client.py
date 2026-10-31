from decimal import Decimal, InvalidOperation
import uuid

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError, Field

from src.application.ports.open_finance import (
    OpenFinanceGateway,
    OpenFinanceNoDisponibleError,
    PerfilOpenFinance,
)
from src.core.config import settings


class _PerfilResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ingreso_mensual: Decimal = Field(gt=0)
    ahorros_liquidos: Decimal = Field(ge=0)
    dti_pct: Decimal = Field(ge=0, le=100)
    sobregiros_12_meses: int = Field(ge=0)
    score: int = Field(ge=0, le=950)


class OpenFinanceHttpClient(OpenFinanceGateway):
    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str | None = None,
    ) -> None:
        self._client = client
        self._base_url = (base_url or settings.OPEN_FINANCE_URL).rstrip("/")

    async def obtener_perfil(self, cliente_id: uuid.UUID) -> PerfilOpenFinance:
        if not self._base_url:
            raise OpenFinanceNoDisponibleError
        try:
            response = await self._client.post(
                f"{self._base_url}/profile", json={"cliente_id": str(cliente_id)}
            )
            response.raise_for_status()
            perfil = _PerfilResponse.model_validate(response.json())
        except (httpx.HTTPError, ValueError, ValidationError, InvalidOperation) as exc:
            raise OpenFinanceNoDisponibleError from exc
        return PerfilOpenFinance(**perfil.model_dump())
