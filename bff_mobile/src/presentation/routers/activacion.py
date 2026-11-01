import json
import uuid

from fastapi import APIRouter, Depends, File, Form, Header, Request, Response, UploadFile, status

from src.infrastructure.gateways.identity_service_gateway import (
    IdentityGatewayError,
    IdentityServiceGateway,
)
from src.presentation.dependencies import get_cliente_autenticado, get_identity_service_gateway
from src.presentation.errors import ApiError
from src.presentation.jwt_validator import ClienteAutenticado
from src.presentation.schemas import (
    IniciarActivacionRequest,
    IniciarActivacionResponse,
    VerificarActivacionResponse,
)

router = APIRouter(prefix="/activacion", tags=["Activación móvil"])

MAX_FRAME_BYTES = 524_288
MAX_BODY_BYTES = 3 * MAX_FRAME_BYTES + 64 * 1024
_SDK_RESULTS = {"COMPLETED", "CANCELLED", "FAILED"}

_RESPUESTAS = {
    401: {"description": "Token ausente, inválido o vencido."},
    403: {"description": "CONSENTIMIENTO_BIOMETRICO_REQUERIDO."},
    404: {"description": "CLIENTE_NO_REGISTRADO o SESION_NO_ENCONTRADA."},
    409: {"description": "SESION_INVALIDA o SESION_CANCELADA."},
    413: {"description": "CAPTURA_DEMASIADO_GRANDE."},
    415: {"description": "FORMATO_NO_SOPORTADO."},
    422: {"description": "DATOS_INVALIDOS."},
    429: {"description": "INTENTOS_AGOTADOS."},
    503: {"description": "SERVICIO_NO_DISPONIBLE (no consume intento)."},
}


async def _leer_frames(uploads: dict[str, UploadFile | None]) -> dict[str, bytes]:
    """Lectura acotada por parte; nunca se carga más de MAX_FRAME_BYTES + 1."""
    frames: dict[str, bytes] = {}
    for name, upload in uploads.items():
        if upload is None:
            raise ApiError(422, "DATOS_INVALIDOS", "Faltan capturas de la prueba de vida.")
        content = await upload.read(MAX_FRAME_BYTES + 1)
        if len(content) > MAX_FRAME_BYTES:
            raise ApiError(413)
        if upload.content_type != "image/jpeg" or not content.startswith(bytes([0xFF, 0xD8, 0xFF])):
            raise ApiError(415)
        frames[name] = content
    return frames


@router.post("/sesiones/{sesion_id}/verificacion", response_model=VerificarActivacionResponse, responses=_RESPUESTAS)
async def verificar_activacion(
    request: Request,
    sesion_id: str,
    metadata: str = Form(...),
    frame_inicio: UploadFile | None = File(None),
    frame_gesto: UploadFile | None = File(None),
    frame_fin: UploadFile | None = File(None),
    correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    cliente: ClienteAutenticado = Depends(get_cliente_autenticado),
    gateway: IdentityServiceGateway = Depends(get_identity_service_gateway),
) -> VerificarActivacionResponse:
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > MAX_BODY_BYTES:
        raise ApiError(413)
    try:
        data = json.loads(metadata)
        sdk_result = data.get("resultado_sdk")
        if sdk_result is None:
            str(data["nonce"])
            dict(data["capturas"])
        elif sdk_result not in _SDK_RESULTS:
            raise ValueError("resultado_sdk desconocido")
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ApiError(422, "DATOS_INVALIDOS", "Metadata de la verificación inválida.") from exc
    frames = {} if sdk_result else await _leer_frames(
        {"frame_inicio": frame_inicio, "frame_gesto": frame_gesto, "frame_fin": frame_fin}
    )
    try:
        result = await gateway.verificar_activacion_movil(
            sesion_id, cliente.correo, metadata, frames, correlation_id or str(uuid.uuid4())
        )
    except IdentityGatewayError as exc:
        raise ApiError.desde_identidad(exc.status_code, exc.detail) from exc
    finally:
        frames.clear()
    return VerificarActivacionResponse.model_validate(result)


@router.post(
    "/sesiones",
    response_model=IniciarActivacionResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_RESPUESTAS,
)
async def iniciar_activacion(
    payload: IniciarActivacionRequest,
    response: Response,
    correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    cliente: ClienteAutenticado = Depends(get_cliente_autenticado),
    gateway: IdentityServiceGateway = Depends(get_identity_service_gateway),
) -> IniciarActivacionResponse:
    """Crea un reto de prueba de vida para una instalación móvil; el correo sale del token."""
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
        raise ApiError.desde_identidad(exc.status_code, exc.detail) from exc

    if result.get("dispositivo_vinculado"):
        response.status_code = status.HTTP_200_OK
    return IniciarActivacionResponse.model_validate(result)
