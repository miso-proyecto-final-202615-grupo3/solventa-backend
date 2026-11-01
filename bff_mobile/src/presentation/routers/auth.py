from fastapi import APIRouter, Depends, HTTPException, status

from src.infrastructure.gateways.identity_service_gateway import (
    IdentityGatewayError,
    IdentityServiceGateway,
)
from src.presentation.dependencies import get_identity_service_gateway
from src.presentation.id_token import correo_desde_id_token
from src.presentation.schemas import LoginRequest, LoginResponse

router = APIRouter(prefix="/auth", tags=["Autenticación"])


@router.post(
    "/login",
    response_model=LoginResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Correo o contraseña inválidos."},
        503: {"description": "El servicio de identidad no está disponible."},
    },
)
async def login(
    payload: LoginRequest,
    gateway: IdentityServiceGateway = Depends(get_identity_service_gateway),
) -> LoginResponse:
    try:
        tokens = await gateway.autenticar_cliente(str(payload.correo), payload.password)
    except IdentityGatewayError as exc:
        # Errores 5xx del MS Identidad se exponen como indisponibilidad, sin filtrar detalles internos.
        if exc.status_code >= 500:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="El servicio de identidad no está disponible.",
            ) from exc
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    correo = correo_desde_id_token(tokens.get("id_token"))
    cliente = None
    if correo:
        try:
            cliente = await gateway.obtener_resumen_movil(
                correo, str(payload.installation_id) if payload.installation_id else None
            )
        except IdentityGatewayError:
            # El login no revela ni queda bloqueado por una consulta auxiliar.
            cliente = None

    return LoginResponse(
        access_token=tokens["access_token"],
        refresh_token=tokens.get("refresh_token"),
        expires_in=tokens.get("expires_in"),
        token_type=tokens.get("token_type", "Bearer"),
        correo=correo,
        cliente=cliente,
    )
