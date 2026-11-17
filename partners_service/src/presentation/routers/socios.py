from fastapi import APIRouter, Depends, Header, HTTPException, status

from src.application.use_cases.registrar_socio_use_case import (
    DuplicateSocioError,
    RegistrarSocioUseCase,
)
from src.presentation.dependencies import (
    get_socio_repository,
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
    try:
        socio = await use_case.ejecutar(
            nombre=payload.nombre,
            correo=str(payload.correo),
            tipo_socio=payload.tipo_socio,
            canal_integracion=payload.canal_integracion,
            actor_id=actor_id,
        )
    except DuplicateSocioError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return SocioResponse.desde_entidad(socio)


@router.get("", response_model=list[SocioResponse])
async def listar_socios(
    repository=Depends(get_socio_repository),
) -> list[SocioResponse]:
    return [SocioResponse.desde_entidad(socio) for socio in await repository.listar()]
