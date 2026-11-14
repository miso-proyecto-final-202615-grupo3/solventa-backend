from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from src.core.config import settings


class HealthResponse(BaseModel):
    status: str
    version: str


router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
)
async def health_check() -> HealthResponse:
    return HealthResponse(status="healthy", version=settings.VERSION)


@router.get("/ready", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def readiness_check(request: Request) -> HealthResponse:
    if not getattr(request.app.state, "schema_ready", False):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no lista.",
        )
    return HealthResponse(status="ready", version=settings.VERSION)
