from src.presentation.schemas.auth_schemas import (
    AutenticarResponse,
    PasswordVerify,
)
from src.presentation.schemas.cliente_schemas import ClienteCreate, ClienteResponse
from src.presentation.schemas.consentimiento_schemas import (
    ActualizarConsentimientoRequest,
    ConsentimientoResponse,
)

__all__ = [
    "AutenticarResponse",
    "ActualizarConsentimientoRequest",
    "ClienteCreate",
    "ClienteResponse",
    "ConsentimientoResponse",
    "PasswordVerify",
]
