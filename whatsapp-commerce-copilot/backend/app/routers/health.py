"""Health check router."""
from fastapi import APIRouter
from app.schemas.api import HealthResponse

router = APIRouter()


@router.get("/api/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="ok")
