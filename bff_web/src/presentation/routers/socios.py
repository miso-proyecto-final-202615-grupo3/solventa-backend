from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from src.infrastructure.gateways.identity_socios_gateway import (
    IdentitySociosGatewayError,
    IdentitySociosGateway,
)
from src.presentation.dependencies import (
    get_identity_socios_gateway,
    require_socios_admin,
)

router = APIRouter(prefix="/socios", tags=["Socios"])


class RegistrarSocioRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    nombre: str = Field(min_length=1, max_length=120)
    correo: EmailStr
    tipo_socio: str = Field(min_length=1, max_length=60)
    canal_integracion: str = Field(min_length=1, max_length=60)


@router.post("", status_code=status.HTTP_201_CREATED)
async def registrar_socio(
    payload: RegistrarSocioRequest,
    actor_id: str = Depends(require_socios_admin),
    correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    gateway: IdentitySociosGateway = Depends(get_identity_socios_gateway),
) -> dict:
    try:
        return await gateway.registrar_socio(
            payload.model_dump(), actor_id, correlation_id
        )
    except IdentitySociosGatewayError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("")
async def listar_socios(
    actor_id: str = Depends(require_socios_admin),
    correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    gateway: IdentitySociosGateway = Depends(get_identity_socios_gateway),
) -> list[dict]:
    try:
        return await gateway.listar_socios(actor_id, correlation_id)
    except IdentitySociosGatewayError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
