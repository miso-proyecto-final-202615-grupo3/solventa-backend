from fastapi import APIRouter, Depends, Header, status

from src.application.use_cases.registrar_socio_use_case import RegistrarSocioUseCase
from src.presentation.dependencies import (
    get_registrar_socio_use_case,
    require_internal_token,
)
from src.presentation.schemas import RegistrarSocioRequest, SocioResponse

router = APIRouter(prefix="/socios", tags=["Socios"])


@router.post(
    "",
    response_model=SocioResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal_token)],
)
async def registrar_socio(
    payload: RegistrarSocioRequest,
    actor_id: str = Header(alias="X-Actor-Id", min_length=1, max_length=100),
    use_case: RegistrarSocioUseCase = Depends(get_registrar_socio_use_case),
) -> SocioResponse:
    socio = await use_case.ejecutar(
        nombre=payload.nombre,
        tipo_socio=payload.tipo_socio,
        canal_integracion=payload.canal_integracion,
        actor_id=actor_id,
    )
    return SocioResponse.desde_entidad(socio)
