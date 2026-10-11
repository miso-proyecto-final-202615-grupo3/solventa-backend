from fastapi import APIRouter, status
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