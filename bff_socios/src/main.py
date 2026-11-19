import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.core.config import settings
from src.core.telemetry import setup_telemetry
from src.infrastructure.gateways.backend_gateway import BackendGatewayError
from src.presentation.routers import (
    clientes,
    health,
    insurancepolicies,
    pagos,
    polizas,
    quotingengine,
)

logger = logging.getLogger(__name__)

app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION)
setup_telemetry(app)


@app.middleware("http")
async def log_internal_errors(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception:
        logger.exception("Error interno al procesar %s %s", request.method, request.url.path)
        raise


@app.exception_handler(BackendGatewayError)
async def backend_gateway_error(request: Request, exc: BackendGatewayError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


app.include_router(health.router)
app.include_router(clientes.router, prefix=settings.API_PREFIX)
app.include_router(quotingengine.router, prefix=settings.API_PREFIX)
app.include_router(insurancepolicies.router, prefix=settings.API_PREFIX)
app.include_router(pagos.router, prefix=settings.API_PREFIX)
app.include_router(polizas.router, prefix=settings.API_PREFIX)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Solventa BFF Socios"}
