"""Cambio de estado del siniestro por un operador (HU4.2.2, decisión N6). Solo red interna y demostración.

No se expone en el BFF. Protegido con `X-Operador-Token` (`OPERADOR_TOKEN`); sin token configurado responde 403.
"""
import hmac
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict

from src.application.use_cases.cambiar_estado_siniestro_use_case import CambiarEstadoSiniestroUseCase
from src.core.config import settings
from src.presentation.dependencies import get_cambiar_estado_siniestro_use_case
from src.presentation.schemas.siniestros import SiniestroResponse

router = APIRouter(prefix="/siniestros", tags=["Operador"])


class CambioEstadoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estado: Literal["REPORTADO", "EN_EVALUACION", "APROBADO", "RECHAZADO", "PAGADO"]


def verificar_operador(x_operador_token: str | None = Header(default=None, alias="X-Operador-Token")) -> None:
    esperado = settings.OPERADOR_TOKEN
    if not esperado or not x_operador_token or not hmac.compare_digest(x_operador_token, esperado):
        raise HTTPException(status_code=403, detail={"codigo": "NO_AUTORIZADO", "mensaje": "No autorizado."})


@router.put("/{siniestro_id}/estado", response_model=SiniestroResponse)
async def cambiar_estado(
    siniestro_id: uuid.UUID,
    payload: CambioEstadoRequest,
    _: None = Depends(verificar_operador),
    use_case: CambiarEstadoSiniestroUseCase = Depends(get_cambiar_estado_siniestro_use_case),
) -> SiniestroResponse:
    """`200` con el siniestro; el mismo estado no genera notificación. `409 TRANSICION_INVALIDA` si no se permite."""
    siniestro, _cambio = await use_case.ejecutar(siniestro_id, payload.estado)
    return SiniestroResponse.desde(siniestro)
