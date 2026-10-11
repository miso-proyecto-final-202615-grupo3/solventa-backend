import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from src.application.ports.identity_provider import (
    IdentityProviderError,
    InvalidCredentialsError,
)
from src.application.use_cases.autenticar_cliente_use_case import (
    AutenticarClienteUseCase,
)
from src.application.use_cases.registrar_cliente_use_case import (
    DuplicateClienteError,
    RegistrarClienteUseCase,
)
from src.application.use_cases.verificar_kyc_use_case import (
    KycClienteNoEncontradoError,
    VerificarKycUseCase,
)
from src.domain.clientes.entities import Cliente
from src.presentation.dependencies import (
    get_autenticar_cliente_use_case,
    get_registrar_cliente_use_case,
    get_verificar_kyc_use_case,
)
from src.presentation.schemas import (
    AutenticarResponse,
    ClienteCreate,
    ClienteResponse,
    PasswordVerify,
)

router = APIRouter(prefix="/clientes", tags=["Clientes"])


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