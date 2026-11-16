"""Traduce los errores de dominio a `{"detail": {"codigo", "mensaje"}}`, igual que el MS Identidad.
El BFF Móvil los convierte al formato común `{codigo, mensaje, correlation_id}`."""
from fastapi import Request
from fastapi.responses import JSONResponse

from src.domain.siniestros.errores import ErrorSiniestro


async def error_siniestro_handler(request: Request, exc: ErrorSiniestro) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": {"codigo": exc.codigo, "mensaje": exc.mensaje}},
    )
