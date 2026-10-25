from fastapi import Request

from src.application.use_cases.generar_cotizacion_use_case import (
    GenerarCotizacionUseCase,
)


def get_generar_cotizacion_use_case(
    request: Request,
) -> GenerarCotizacionUseCase:
    return request.app.state.generar_cotizacion_use_case
