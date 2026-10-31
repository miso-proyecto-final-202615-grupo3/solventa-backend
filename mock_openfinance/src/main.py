import asyncio
import os
import uuid
from decimal import Decimal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field


app = FastAPI(title="Solventa Mock Open Finance", version="0.1.0")


class PerfilRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cliente_id: uuid.UUID


class PerfilResponse(BaseModel):
    ingreso_mensual: Decimal = Field(gt=0)
    ahorros_liquidos: Decimal = Field(ge=0)
    dti_pct: Decimal = Field(ge=0, le=100)
    sobregiros_12_meses: int = Field(ge=0)
    score: int = Field(ge=0, le=950)


@app.post("/profile", response_model=PerfilResponse)
async def obtener_perfil(_payload: PerfilRequest) -> PerfilResponse:
    delay_ms = max(0, int(os.getenv("MOCK_OPENFINANCE_DELAY_MS", "0")))
    if delay_ms:
        await asyncio.sleep(delay_ms / 1000)

    if os.getenv("MOCK_OPENFINANCE_STATUS", "AVAILABLE").upper() != "AVAILABLE":
        raise HTTPException(
            status_code=503,
            detail="Proveedor Open Finance temporalmente no disponible.",
        )

    return PerfilResponse(
        ingreso_mensual=Decimal(
            os.getenv("MOCK_OPENFINANCE_INCOME", "8500000")
        ),
        ahorros_liquidos=Decimal(
            os.getenv("MOCK_OPENFINANCE_SAVINGS", "25500000")
        ),
        dti_pct=Decimal(os.getenv("MOCK_OPENFINANCE_DTI", "28")),
        sobregiros_12_meses=int(
            os.getenv("MOCK_OPENFINANCE_OVERDRAFTS", "0")
        ),
        score=int(os.getenv("MOCK_OPENFINANCE_SCORE", "820")),
    )
