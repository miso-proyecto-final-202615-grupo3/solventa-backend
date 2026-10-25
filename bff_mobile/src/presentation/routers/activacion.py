import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status

from src.core.config import settings
from src.infrastructure.gateways.identity_service_gateway import (
    IdentityGatewayError,
    IdentityServiceGateway,
)
from src.presentation.dependencies import get_identity_service_gateway
from src.presentation.schemas import (
    IniciarActivacionRequest,
    IniciarActivacionResponse,
)

router = APIRouter(prefix="/activacion", tags=["Activación móvil"])


def _demo_sin_jwt_habilitada() -> bool:
    return settings.ENVIRONMENT.lower() in {"development", "dev", "local"} and (
        settings.ALLOW_DEMO_ACTIVATION_WITHOUT_JWT
    )


@router.post(
    "/sesiones",
    response_model=IniciarActivacionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def iniciar_activacion(
    payload: IniciarActivacionRequest,
    correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    gateway: IdentityServiceGateway = Depends(get_identity_service_gateway),
) -> IniciarActivacionResponse:
    """Crea un reto de prueba de vida para una instalación móvil."""
    if not _demo_sin_jwt_habilitada():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere autenticación para iniciar la activación.",
        )
    if payload.correo is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El correo es obligatorio durante la demostración local.",
        )
    try:
        result = await gateway.iniciar_activacion_movil(
            str(payload.correo),
            {
                "installation_id": str(payload.installation_id),
                "plataforma": payload.plataforma,
                "modelo": payload.modelo,
                "version_so": payload.version_so,
            },
            correlation_id or str(uuid.uuid4()),
        )
    except IdentityGatewayError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return IniciarActivacionResponse.model_validate(result)
