from fastapi import APIRouter, Depends, HTTPException, status

from src.application.use_cases.consultar_catalogo_use_case import (
    ConsultarCatalogoUseCase,
    ProductoNoEncontradoError,
)
from src.presentation.dependencies import get_consultar_catalogo_use_case
from src.presentation.schemas.producto_schemas import (
    ProductoResponse,
    producto_response,
)

router = APIRouter(prefix="/productos", tags=["Productos"])


@router.get("", response_model=list[ProductoResponse])
async def listar_productos(
    use_case: ConsultarCatalogoUseCase = Depends(get_consultar_catalogo_use_case),
) -> list[ProductoResponse]:
    return [producto_response(p) for p in await use_case.listar()]


@router.get("/{codigo}", response_model=ProductoResponse)
async def obtener_producto(
    codigo: str,
    use_case: ConsultarCatalogoUseCase = Depends(get_consultar_catalogo_use_case),
) -> ProductoResponse:
    try:
        return producto_response(await use_case.obtener(codigo))
    except ProductoNoEncontradoError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ramo de seguro no encontrado.",
        ) from exc
