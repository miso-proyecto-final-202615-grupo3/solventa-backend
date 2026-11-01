import uuid
import json

from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Response, UploadFile, status

from src.application.ports.identity_provider import (
    IdentityProviderError,
    InvalidCredentialsError,
)
from src.application.use_cases.autenticar_cliente_use_case import (
    AutenticarClienteUseCase,
)
from src.application.use_cases.gestionar_consentimiento_use_case import (
    ConsentimientoNoEncontradoError,
    ConsentimientoNoOtorgadoError,
    GestionarConsentimientoUseCase,
    PerfilClienteNoEncontradoError,
)
from src.application.use_cases.registrar_cliente_use_case import (
    DuplicateClienteError,
    RegistrarClienteUseCase,
)
from src.application.use_cases.verificar_kyc_use_case import (
    KycClienteNoEncontradoError,
    VerificarKycUseCase,
)
from src.application.use_cases.iniciar_activacion_movil_use_case import (
    ClienteNoRegistradoError,
    ConsentimientoBiometricoRequeridoError,
    IniciarActivacionMovilUseCase,
    IntentosAgotadosError,
)
from src.application.ports.liveness import LivenessAdapterUnavailableError
from src.application.use_cases.consultar_resumen_movil_use_case import (
    ConsultarResumenMovilUseCase,
    ResumenClienteNoEncontradoError,
)
from src.application.use_cases.verificar_activacion_movil_use_case import (
    CapturaActivacionInvalidaError,
    IntentosActivacionAgotadosError,
    SesionActivacionCanceladaError,
    SesionActivacionInvalidaError,
    VerificacionPruebaVidaNoDisponibleError,
    VerificarActivacionMovilUseCase,
)
from src.domain.activacion_movil.entities import DatosDispositivo
from src.domain.clientes.entities import Cliente
from src.presentation.dependencies import (
    get_autenticar_cliente_use_case,
    get_consultar_resumen_movil_use_case,
    get_gestionar_consentimiento_use_case,
    get_registrar_cliente_use_case,
    get_verificar_kyc_use_case,
    get_iniciar_activacion_movil_use_case,
    get_verificar_activacion_movil_use_case,
)
from src.presentation.schemas import (
    AutenticarResponse,
    ActualizarConsentimientoRequest,
    ClienteCreate,
    ClienteResponse,
    ConsentimientoResponse,
    PasswordVerify,
    IniciarActivacionMovilRequest,
    IniciarActivacionMovilResponse,
    VerificarActivacionMovilResponse,
    ResumenMovilResponse,
)

router = APIRouter(prefix="/clientes", tags=["Clientes"])


MAX_FRAME_BYTES = 524_288
_FRAME_NAMES = ("frame_inicio", "frame_gesto", "frame_fin")


def _error(status_code: int, codigo: str, mensaje: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"codigo": codigo, "mensaje": mensaje})


async def _leer_frames(uploads: dict[str, UploadFile | None]) -> dict[str, bytes]:
    """Lectura acotada: nunca se lee más de MAX_FRAME_BYTES + 1 por parte."""
    frames: dict[str, bytes] = {}
    for name, upload in uploads.items():
        if upload is None:
            raise _error(422, "DATOS_INVALIDOS", "Faltan capturas de la prueba de vida.")
        content = await upload.read(MAX_FRAME_BYTES + 1)
        if len(content) > MAX_FRAME_BYTES:
            raise _error(413, "CAPTURA_DEMASIADO_GRANDE", "La captura supera el tamaño permitido.")
        if upload.content_type != "image/jpeg" or not content.startswith(b"\xff\xd8\xff"):
            raise _error(415, "FORMATO_NO_SOPORTADO", "Las capturas deben ser JPEG.")
        frames[name] = content
    return frames


@router.post("/activacion-movil/sesiones/{sesion_id}/verificacion", response_model=VerificarActivacionMovilResponse)
async def verificar_activacion_movil(
    sesion_id: str,
    correo: str = Form(...),
    metadata: str = Form(...),
    frame_inicio: UploadFile | None = File(None),
    frame_gesto: UploadFile | None = File(None),
    frame_fin: UploadFile | None = File(None),
    correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    use_case: VerificarActivacionMovilUseCase = Depends(get_verificar_activacion_movil_use_case),
) -> VerificarActivacionMovilResponse:
    try:
        data = json.loads(metadata)
        sdk_result = data.get("resultado_sdk")
        nonce = None if sdk_result else str(data["nonce"])
        capturas = {} if sdk_result else dict(data["capturas"])
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise _error(422, "DATOS_INVALIDOS", "Metadata de la verificación inválida.") from exc
    if sdk_result is not None and sdk_result not in {"COMPLETED", "CANCELLED", "FAILED"}:
        raise _error(422, "DATOS_INVALIDOS", "Resultado del SDK desconocido.")
    frames = {} if sdk_result else await _leer_frames(
        {"frame_inicio": frame_inicio, "frame_gesto": frame_gesto, "frame_fin": frame_fin}
    )
    try:
        result = await use_case.ejecutar(
            correo, sesion_id, nonce, frames, capturas, correlation_id or str(uuid4()), sdk_result=sdk_result
        )
    except CapturaActivacionInvalidaError as exc:
        raise _error(422, "CAPTURA_INVALIDA", "Las capturas no se pudieron evaluar.") from exc
    except SesionActivacionCanceladaError as exc:
        raise _error(409, "SESION_CANCELADA", "La verificación fue cancelada.") from exc
    except SesionActivacionInvalidaError as exc:
        raise _error(409, "SESION_INVALIDA", "La sesión de activación no es válida.") from exc
    except IntentosActivacionAgotadosError as exc:
        raise _error(429, "INTENTOS_AGOTADOS", "Se agotaron los intentos disponibles.") from exc
    except VerificacionPruebaVidaNoDisponibleError as exc:
        raise _error(503, "SERVICIO_NO_DISPONIBLE", "La verificación no está disponible.") from exc
    finally:
        frames.clear()
    return VerificarActivacionMovilResponse(
        resultado=result.resultado, folio=result.folio, intento=result.intento,
        intentos_restantes=result.intentos_restantes,
        dispositivo_vinculado=result.dispositivo_vinculado,
        vinculado_en=result.vinculado_en, motivo=result.motivo,
    )


@router.post(
    "/activacion-movil/sesiones",
    response_model=IniciarActivacionMovilResponse,
    status_code=status.HTTP_201_CREATED,
)
async def iniciar_activacion_movil(
    payload: IniciarActivacionMovilRequest,
    response: Response,
    correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    use_case: IniciarActivacionMovilUseCase = Depends(
        get_iniciar_activacion_movil_use_case
    ),
) -> IniciarActivacionMovilResponse:
    try:
        resultado = await use_case.ejecutar(
            str(payload.correo),
            DatosDispositivo(
                installation_id=payload.installation_id,
                plataforma=payload.plataforma,
                modelo=payload.modelo,
                version_so=payload.version_so,
            ),
            correlation_id or str(uuid4()),
        )
    except ClienteNoRegistradoError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"codigo": "CLIENTE_NO_REGISTRADO", "mensaje": "Cliente no registrado."},
        ) from exc
    except ConsentimientoBiometricoRequeridoError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"codigo": "CONSENTIMIENTO_BIOMETRICO_REQUERIDO", "mensaje": "Consentimiento biométrico requerido."},
        ) from exc
    except IntentosAgotadosError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"codigo": "INTENTOS_AGOTADOS", "mensaje": "Se agotaron los intentos disponibles."},
        ) from exc
    except LivenessAdapterUnavailableError as exc:
        raise _error(503, "SERVICIO_NO_DISPONIBLE", "La activación no está disponible.") from exc

    if resultado.dispositivo_vinculado:
        response.status_code = status.HTTP_200_OK
    return IniciarActivacionMovilResponse(
        dispositivo_vinculado=resultado.dispositivo_vinculado,
        sesion_id=resultado.sesion_id,
        expira_en=resultado.expira_en,
        captura=resultado.captura,
        intentos_restantes=resultado.intentos_restantes,
    )


@router.get("/resumen-movil", response_model=ResumenMovilResponse)
async def consultar_resumen_movil(
    correo: str = Query(..., max_length=254),
    installation_id: uuid.UUID | None = Query(None),
    use_case: ConsultarResumenMovilUseCase = Depends(get_consultar_resumen_movil_use_case),
) -> ResumenMovilResponse:
    """Consulta interna del BFF; la autenticación del usuario ocurre en el BFF."""
    try:
        resumen = await use_case.ejecutar(correo, installation_id)
    except ResumenClienteNoEncontradoError as exc:
        raise _error(404, "CLIENTE_NO_REGISTRADO", "Cliente no registrado.") from exc
    return ResumenMovilResponse(
        id=resumen.id, nombre=resumen.nombre, estado_kyc=resumen.estado_kyc,
        dispositivo_vinculado=resumen.dispositivo_vinculado,
    )


def _cliente_response(cliente: Cliente) -> ClienteResponse:
    return ClienteResponse(
        id=cliente.id.value,
        nombres=cliente.nombres,
        apellidos=cliente.apellidos,
        tipo_documento=cliente.tipo_documento,
        numero_identificacion=cliente.numero_identificacion,
        correo=cliente.correo,
        fecha_nacimiento=cliente.fecha_nacimiento,
        pais_residencia=cliente.pais_residencia,
        telefono=cliente.telefono,
        estado_kyc=cliente.estado_kyc,
        fecha_creacion=cliente.fecha_creacion,
        fecha_actualizacion=cliente.fecha_actualizacion,
    )


@router.post(
    "/registro",
    response_model=ClienteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def registrar_cliente(
    payload: ClienteCreate,
    use_case: RegistrarClienteUseCase = Depends(get_registrar_cliente_use_case),
) -> ClienteResponse:
    try:
        cliente = await use_case.ejecutar(payload)
    except DuplicateClienteError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.detalle,
        ) from exc
    except IdentityProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo crear la identidad del cliente.",
        ) from exc

    return _cliente_response(cliente)


@router.post(
    "/autenticar",
    response_model=AutenticarResponse,
    status_code=status.HTTP_200_OK,
)
async def autenticar_cliente(
    payload: PasswordVerify,
    use_case: AutenticarClienteUseCase = Depends(get_autenticar_cliente_use_case),
) -> AutenticarResponse:
    try:
        resultado = await use_case.ejecutar(payload)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas.",
        ) from exc
    except IdentityProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo autenticar en este momento.",
        ) from exc

    return AutenticarResponse(
        access_token=resultado.access_token,
        id_token=resultado.id_token,
        refresh_token=resultado.refresh_token,
        expires_in=resultado.expires_in,
        token_type=resultado.token_type,
    )


@router.put(
    "/{cliente_id}/consentimiento",
    response_model=ConsentimientoResponse,
    status_code=status.HTTP_200_OK,
)
@router.post(
    "/{cliente_id}/consentimiento/revocar",
    response_model=ConsentimientoResponse,
    status_code=status.HTTP_200_OK,
    deprecated=True,
)
async def actualizar_consentimiento(
    cliente_id: uuid.UUID,
    payload: ActualizarConsentimientoRequest,
    use_case: GestionarConsentimientoUseCase = Depends(
        get_gestionar_consentimiento_use_case
    ),
) -> ConsentimientoResponse:
    try:
        consentimiento = await use_case.actualizar_consentimiento(
            cliente_id, payload.estado
        )
    except ConsentimientoNoEncontradoError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El cliente no tiene un consentimiento registrado.",
        ) from exc
    return ConsentimientoResponse.model_validate(consentimiento)


@router.get(
    "/{cliente_id}/perfil",
    response_model=ClienteResponse,
    status_code=status.HTTP_200_OK,
)
async def obtener_perfil_cliente(
    cliente_id: uuid.UUID,
    use_case: GestionarConsentimientoUseCase = Depends(
        get_gestionar_consentimiento_use_case
    ),
) -> ClienteResponse:
    try:
        perfil = await use_case.obtener_perfil_cliente(cliente_id)
    except ConsentimientoNoOtorgadoError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El cliente no ha autorizado la consulta de su perfil financiero.",
        ) from exc
    except PerfilClienteNoEncontradoError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El cliente indicado no existe.",
        ) from exc
    return ClienteResponse.model_validate(perfil)


@router.post(
    "/{cliente_id}/verificar-kyc",
    response_model=ClienteResponse,
    status_code=status.HTTP_200_OK,
)
async def verificar_kyc(
    cliente_id: uuid.UUID,
    use_case: VerificarKycUseCase = Depends(get_verificar_kyc_use_case),
) -> ClienteResponse:
    try:
        cliente = await use_case.ejecutar(cliente_id)
    except KycClienteNoEncontradoError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El cliente indicado no existe.",
        ) from exc

    return _cliente_response(cliente)
