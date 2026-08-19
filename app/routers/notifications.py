from fastapi import APIRouter, Depends, Query, status

from app.core.security import ServiceIdentity
from app.core.state_machine import NotificationStatus
from app.dependencies import get_current_service, get_notification_service
from app.schemas.notification import NotificationCreate, NotificationResponse
from app.schemas.pagination import PaginatedResponse
from app.services.notification import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.post(
    "",
    response_model=NotificationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a notification",
)
async def create_notification(
    payload: NotificationCreate,
    service: ServiceIdentity = Depends(get_current_service),
    notification_service: NotificationService = Depends(get_notification_service),
) -> NotificationResponse:
    """
    Creates an internal notification request and schedules asynchronous delivery.
    Requires authenticated platform service token.
    """
    return await notification_service.create_notification(service, payload)


@router.get(
    "/{notification_id}",
    response_model=NotificationResponse,
    summary="Get notification by ID",
)
async def get_notification(
    notification_id: str,
    service: ServiceIdentity = Depends(get_current_service),
    notification_service: NotificationService = Depends(get_notification_service),
) -> NotificationResponse:
    """Retrieves status and tracking metadata for a specific notification."""
    return await notification_service.get_notification(service, notification_id)


@router.get(
    "",
    response_model=PaginatedResponse[NotificationResponse],
    summary="List notifications",
)
async def list_notifications(
    status: NotificationStatus | None = Query(None, description="Filter by notification status"),
    limit: int = Query(50, ge=1, le=1000, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
    service: ServiceIdentity = Depends(get_current_service),
    notification_service: NotificationService = Depends(get_notification_service),
) -> PaginatedResponse[NotificationResponse]:
    """Lists notifications for the authenticated service."""
    items, total = await notification_service.list_notifications(
        service=service,
        status=status,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )
