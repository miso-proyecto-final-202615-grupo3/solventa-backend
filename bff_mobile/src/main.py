from fastapi import FastAPI

from src.core.config import settings
from src.core.correlation import CorrelationIdMiddleware
from src.core.telemetry import setup_telemetry
from src.presentation.errors import ApiError, api_error_handler
from src.presentation.routers import activacion, auth, health, quotingengine

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

setup_telemetry(app)
app.add_middleware(CorrelationIdMiddleware, service="bff_mobile")
app.add_exception_handler(ApiError, api_error_handler)

app.include_router(health.router)
app.include_router(auth.router, prefix=settings.API_PREFIX)
app.include_router(activacion.router, prefix=settings.API_PREFIX)
app.include_router(quotingengine.router, prefix=settings.API_PREFIX)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Solventa BFF Mobile"}
