from fastapi import APIRouter, Depends, HTTPException, status

from src.application.use_cases.registrar_cliente_use_case import (
    DuplicateClienteError,
    IdentityProviderError,
    RegistrarClienteUseCase,
)
from src.presentation.dependencies import get_registrar_cliente_use_case
from src.presentation.schemas import ClienteCreate, ClienteResponse

router = APIRouter(prefix="/clientes", tags=["Clientes"])


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