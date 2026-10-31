import uuid
import json

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status

from src.infrastructure.gateways.identity_service_gateway import (
    IdentityGatewayError,
    IdentityServiceGateway,
)
from src.presentation.dependencies import get_cliente_autenticado, get_identity_service_gateway
from src.presentation.jwt_validator import ClienteAutenticado
from src.presentation.schemas import (
    IniciarActivacionRequest,
    IniciarActivacionResponse,
    VerificarActivacionResponse,
)

router = APIRouter(prefix="/activacion", tags=["Activación móvil"])


@router.post("/sesiones/{sesion_id}/verificacion", response_model=VerificarActivacionResponse)
async def verificar_activacion(
    sesion_id: str, metadata: str = Form(...),
    frame_inicio: UploadFile = File(...), frame_gesto: UploadFile = File(...), frame_fin: UploadFile = File(...),
    correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    cliente: ClienteAutenticado = Depends(get_cliente_autenticado),
    gateway: IdentityServiceGateway = Depends(get_identity_service_gateway),
) -> VerificarActivacionResponse:
    uploads = {"frame_inicio": frame_inicio, "frame_gesto": frame_gesto, "frame_fin": frame_fin}
    frames = {name: await upload.read(524289) for name, upload in uploads.items()}
    if any(len(value) > 524288 for value in frames.values()):
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, {"codigo": "CAPTURA_DEMASIADO_GRANDE"})
    if any(upload.content_type != "image/jpeg" or not frames[name].startswith(b"\xff\xd8\xff") for name, upload in uploads.items()):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, {"codigo": "FORMATO_NO_SOPORTADO"})
    try:
        json.loads(metadata)["nonce"]
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, {"codigo": "DATOS_INVALIDOS"}) from exc
    try:
        result = await gateway.verificar_activacion_movil(sesion_id, cliente.correo, metadata, frames, correlation_id or str(uuid.uuid4()))
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
    cliente: ClienteAutenticado = Depends(get_cliente_autenticado),
    gateway: IdentityServiceGateway = Depends(get_identity_service_gateway),
) -> IniciarActivacionResponse:
    """Crea un reto de prueba de vida para una instalación móvil."""
    try:
        result = await gateway.iniciar_activacion_movil(
            cliente.correo,
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
