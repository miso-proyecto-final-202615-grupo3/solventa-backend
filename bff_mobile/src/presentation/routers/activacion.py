import uuid

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status

from src.core.config import settings
from src.infrastructure.gateways.identity_service_gateway import (
    IdentityGatewayError,
    IdentityServiceGateway,
)
from src.presentation.dependencies import get_identity_service_gateway
from src.presentation.schemas import (
    IniciarActivacionRequest,
    IniciarActivacionResponse,
    VerificarActivacionResponse,
)

router = APIRouter(prefix="/activacion", tags=["Activación móvil"])


def _demo_sin_jwt_habilitada() -> bool:
    return settings.ENVIRONMENT.lower() in {"development", "dev", "local"} and (
        settings.ALLOW_DEMO_ACTIVATION_WITHOUT_JWT
    )


@router.post("/sesiones/{sesion_id}/verificacion", response_model=VerificarActivacionResponse)
async def verificar_activacion(
    sesion_id: str, correo: str = Form(...), nonce: str = Form(...),
    frame_inicio: UploadFile = File(...), frame_gesto: UploadFile = File(...), frame_fin: UploadFile = File(...),
    correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    gateway: IdentityServiceGateway = Depends(get_identity_service_gateway),
) -> VerificarActivacionResponse:
    if not _demo_sin_jwt_habilitada():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Se requiere autenticación para verificar la activación.")
    frames = {"frame_inicio": await frame_inicio.read(524289), "frame_gesto": await frame_gesto.read(524289), "frame_fin": await frame_fin.read(524289)}
    if any(len(value) > 524288 or not value.startswith(b"\xff\xd8\xff") for value in frames.values()):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, {"codigo": "EVIDENCIA_INVALIDA"})
    try:
        result = await gateway.verificar_activacion_movil(sesion_id, correo, nonce, frames, correlation_id or str(uuid.uuid4()))
    except IdentityGatewayError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc
    return VerificarActivacionResponse.model_validate(result)


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
