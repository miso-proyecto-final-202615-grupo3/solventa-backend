"""Formato de error común de los endpoints nuevos del BFF Móvil (decisión D6).

`{"codigo", "mensaje", "correlation_id"}`. `/auth/login` conserva su formato original (`detail`).
"""
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse

_MENSAJES = {
    400: ("DATOS_INVALIDOS", "La solicitud no es válida."),
    401: ("NO_AUTENTICADO", "Se requiere un token válido."),
    403: ("NO_AUTORIZADO", "No tienes permiso para esta operación."),
    404: ("NO_ENCONTRADO", "No se encontró el recurso."),
    409: ("SESION_INVALIDA", "La sesión de activación no es válida."),
    413: ("CAPTURA_DEMASIADO_GRANDE", "La captura supera el tamaño permitido."),
    415: ("FORMATO_NO_SOPORTADO", "Las capturas deben ser JPEG."),
    422: ("DATOS_INVALIDOS", "La solicitud no es válida."),
    429: ("INTENTOS_AGOTADOS", "Se agotaron los intentos disponibles."),
}


class ApiError(Exception):
    def __init__(self, status_code: int, codigo: str | None = None, mensaje: str | None = None) -> None:
        defecto = _MENSAJES.get(status_code, ("SERVICIO_NO_DISPONIBLE", "El servicio no está disponible."))
        self.status_code = status_code
        self.codigo = codigo or defecto[0]
        self.mensaje = mensaje or defecto[1]
        super().__init__(self.codigo)

    @classmethod
    def desde_identidad(cls, status_code: int, detail) -> "ApiError":
        """Traduce un error del MS Identidad sin filtrar detalles internos de los 5xx."""
        if status_code >= 500:
            return cls(503, "SERVICIO_NO_DISPONIBLE", "El servicio no está disponible.")
        if isinstance(detail, dict):
            return cls(status_code, detail.get("codigo"), detail.get("mensaje"))
        return cls(status_code)


def correlation_id_de(request: Request) -> str:
    return request.headers.get("X-Correlation-Id") or str(uuid.uuid4())


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    correlation_id = correlation_id_de(request)
    return JSONResponse(
        status_code=exc.status_code,
        content={"codigo": exc.codigo, "mensaje": exc.mensaje, "correlation_id": correlation_id},
        headers={"X-Correlation-Id": correlation_id},
    )
