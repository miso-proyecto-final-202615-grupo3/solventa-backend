import asyncio
import os
import unicodedata

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

app = FastAPI(title="Solventa Mock Open Data", version="0.1.0")


class RiesgoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    municipio: str = Field(min_length=2, max_length=100)
    zona: str = Field(min_length=1, max_length=20)
    estrato: int = Field(ge=1, le=6)


class RiesgoResponse(BaseModel):
    categoria: str
    id_territorial: float
    ir_publico: float


@app.post("/risk", response_model=RiesgoResponse)
async def obtener_riesgo(payload: RiesgoRequest) -> RiesgoResponse:
    delay_ms = max(0, int(os.getenv("MOCK_OPENDATA_DELAY_MS", "0")))
    if delay_ms:
        await asyncio.sleep(delay_ms / 1000)

    if os.getenv("MOCK_OPENDATA_STATUS", "AVAILABLE").upper() != "AVAILABLE":
        raise HTTPException(
            status_code=503,
            detail="Fuente Open Data temporalmente no disponible.",
        )

    configured_category = os.getenv("MOCK_OPENDATA_CATEGORY", "").upper()
    if configured_category:
        category = configured_category
    elif (
        _normalizar_municipio(payload.municipio) in {"bogota", "bogota d.c."}
        and payload.zona.upper() == "URBANA"
        and payload.estrato == 4
    ):
        category = "BAJO_RIESGO"
    else:
        category = "ESTANDAR"

    indicators = {
        "BAJO_RIESGO": (0.95, 1.00),
        "ESTANDAR": (1.00, 1.00),
        "RIESGO_ELEVADO": (1.10, 1.10),
    }
    if category not in indicators:
        category = "ESTANDAR"
    id_territorial, ir_publico = indicators[category]
    return RiesgoResponse(
        categoria=category,
        id_territorial=id_territorial,
        ir_publico=ir_publico,
    )


def _normalizar_municipio(municipio: str) -> str:
    normalizado = unicodedata.normalize("NFKD", municipio.casefold())
    return "".join(char for char in normalizado if not unicodedata.combining(char))
