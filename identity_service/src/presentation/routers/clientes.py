import uuid

from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

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
from src.domain.activacion_movil.entities import DatosDispositivo
from src.domain.clientes.entities import Cliente
from src.presentation.dependencies import (
    get_db,
    get_autenticar_cliente_use_case,
    get_gestionar_consentimiento_use_case,
    get_registrar_cliente_use_case,
    get_verificar_kyc_use_case,
    get_iniciar_activacion_movil_use_case,
)
from src.infrastructure.persistence.models import ClienteModel, DispositivoVinculadoModel
from src.presentation.schemas import (
    AutenticarResponse,
    ActualizarConsentimientoRequest,
    ClienteCreate,
    ClienteResponse,
    ConsentimientoResponse,
    PasswordVerify,
    IniciarActivacionMovilRequest,
    IniciarActivacionMovilResponse,
)

router = APIRouter(prefix="/clientes", tags=["Clientes"])


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
            detail={"codigo": "CONSENTIMIENTO_REQUERIDO", "mensaje": "Consentimiento biométrico requerido."},
        ) from exc
    except IntentosAgotadosError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"codigo": "INTENTOS_AGOTADOS", "mensaje": "Se agotaron los intentos disponibles."},
        ) from exc

    if resultado.dispositivo_vinculado:
        response.status_code = status.HTTP_200_OK
    return IniciarActivacionMovilResponse(
        dispositivo_vinculado=resultado.dispositivo_vinculado,
        sesion_id=resultado.sesion_id,
        expira_en=resultado.expira_en,
        captura=resultado.captura,
        intentos_restantes=resultado.intentos_restantes,
    )


@router.get("/resumen-movil")
async def consultar_resumen_movil(
    correo: str = Query(...),
    installation_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Consulta interna del BFF; la autenticación del usuario ocurre en el BFF."""
    result = await db.execute(
        select(ClienteModel).where(func.lower(ClienteModel.correo) == correo.lower())
    )
    cliente = result.scalar_one_or_none()
    if cliente is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado.")
    vinculado = False
    if installation_id is not None:
        vinculo = await db.execute(
            select(DispositivoVinculadoModel.id).where(
                DispositivoVinculadoModel.cliente_id == cliente.id,
                DispositivoVinculadoModel.installation_id == installation_id,
                DispositivoVinculadoModel.estado == "ACTIVO",
            )
        )
        vinculado = vinculo.scalar_one_or_none() is not None
    return {
        "id": str(cliente.id),
        "nombre": f"{cliente.nombres} {cliente.apellidos}".strip(),
        "estado_kyc": cliente.estado_kyc.value,
        "dispositivo_vinculado": vinculado,
    }


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
