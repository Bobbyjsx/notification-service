from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint for Cloud Run and container liveness probes."""
    return {"status": "ok", "service": settings.service_name}
