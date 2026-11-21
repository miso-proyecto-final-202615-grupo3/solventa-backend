import uuid

from fastapi import APIRouter, Depends, Header, Response

from src.infrastructure.gateways.identity_service_gateway import IdentityGatewayError, IdentityServiceGateway
from src.presentation.dependencies import get_cliente_id, get_identity_service_gateway
from src.presentation.errors import ApiError
from src.presentation.schemas import RegistrarPushRequest

router = APIRouter(prefix="/dispositivos", tags=["Dispositivos"])


def _correlation(correlation_id: str | None) -> str:
    return correlation_id or str(uuid.uuid4())


@router.put("/push", status_code=204)
async def registrar_push(payload: RegistrarPushRequest, correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"), cliente_id: str = Depends(get_cliente_id), gateway: IdentityServiceGateway = Depends(get_identity_service_gateway)) -> Response:
    try:
        await gateway.registrar_token_push(cliente_id, str(payload.installation_id), payload.token, payload.plataforma, _correlation(correlation_id))
    except IdentityGatewayError as exc:
        raise ApiError.desde_identidad(exc.status_code, exc.detail) from exc
    return Response(status_code=204)


@router.delete("/push", status_code=204)
async def eliminar_push(installation_id: uuid.UUID, correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"), cliente_id: str = Depends(get_cliente_id), gateway: IdentityServiceGateway = Depends(get_identity_service_gateway)) -> Response:
    try:
        await gateway.eliminar_token_push(cliente_id, str(installation_id), _correlation(correlation_id))
    except IdentityGatewayError as exc:
        raise ApiError.desde_identidad(exc.status_code, exc.detail) from exc
    return Response(status_code=204)
