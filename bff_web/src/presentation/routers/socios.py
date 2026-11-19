from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
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


async def _api_keys(gateway: IdentitySociosGateway, method: str, socio_id: UUID, key_id: UUID | None = None):
    try:
        return await gateway.api_keys(method, str(socio_id), str(key_id) if key_id else None)
    except IdentitySociosGatewayError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/{socio_id}/api-keys", status_code=201)
async def crear_api_key(socio_id: UUID, response: Response, actor_id: str = Depends(require_socios_admin), gateway: IdentitySociosGateway = Depends(get_identity_socios_gateway)):
    response.headers["Cache-Control"] = "no-store"
    return await _api_keys(gateway, "POST", socio_id)


@router.get("/{socio_id}/api-keys")
async def listar_api_keys(socio_id: UUID, actor_id: str = Depends(require_socios_admin), gateway: IdentitySociosGateway = Depends(get_identity_socios_gateway)):
    return await _api_keys(gateway, "GET", socio_id)


@router.get("/{socio_id}/api-keys/{key_id}")
async def consultar_api_key(socio_id: UUID, key_id: UUID, actor_id: str = Depends(require_socios_admin), gateway: IdentitySociosGateway = Depends(get_identity_socios_gateway)):
    return await _api_keys(gateway, "GET", socio_id, key_id)


@router.delete("/{socio_id}/api-keys/{key_id}", status_code=204)
async def borrar_api_key(socio_id: UUID, key_id: UUID, actor_id: str = Depends(require_socios_admin), gateway: IdentitySociosGateway = Depends(get_identity_socios_gateway)):
    await _api_keys(gateway, "DELETE", socio_id, key_id)
    return Response(status_code=204)
