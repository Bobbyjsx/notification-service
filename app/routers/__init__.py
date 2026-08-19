"""FastAPI routers package."""

from app.routers.events import router as events_router
from app.routers.health import router as health_router
from app.routers.notifications import router as notifications_router
from app.routers.tasks import router as tasks_router
from app.routers.webhooks import router as webhooks_router

__all__ = [
    "health_router",
    "notifications_router",
    "events_router",
    "tasks_router",
    "webhooks_router",
]
