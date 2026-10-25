from decimal import Decimal
import uuid

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.application.ports.open_finance import OpenFinanceProvider
from src.core.config import settings
from src.domain.perfilamiento.entities import PerfilOpenFinance


class PerfilOpenFinanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ingreso_mensual: Decimal = Field(gt=0)
    ahorros_liquidos: Decimal = Field(ge=0)
    dti_pct: Decimal = Field(ge=0)
    sobregiros_12_meses: int = Field(ge=0)
    score: int = Field(ge=0, le=950)


class OpenFinanceUnavailableError(Exception):
    pass


class OpenFinanceHttpClient(OpenFinanceProvider):
    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str | None = None,
    ) -> None:
        self.client = client
        self.base_url = (base_url or settings.OPEN_FINANCE_URL).rstrip("/")

    async def obtener_perfil_financiero(
        self, cliente_id: uuid.UUID
    ) -> PerfilOpenFinance:
        if not self.base_url:
            raise OpenFinanceUnavailableError
        try:
            response = await self.client.post(
                f"{self.base_url}/profile",
                json={"cliente_id": str(cliente_id)},
            )
            response.raise_for_status()
            payload = PerfilOpenFinanceResponse.model_validate(response.json())
        except (httpx.HTTPError, ValueError, ValidationError) as exc:
            raise OpenFinanceUnavailableError from exc

        return PerfilOpenFinance(
            ingreso_mensual=payload.ingreso_mensual,
            ahorros_liquidos=payload.ahorros_liquidos,
            dti_pct=payload.dti_pct,
            sobregiros_12_meses=payload.sobregiros_12_meses,
            score=payload.score,
        )
