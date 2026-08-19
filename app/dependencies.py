from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.cloud.firestore_v1.async_client import AsyncClient

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import AuthenticationError
from app.core.security import ServiceIdentity, verify_service_token
from app.integrations.base import EmailProvider
from app.integrations.cloud_tasks import CloudTasksDispatcher
from app.integrations.mock import MockEmailProvider
from app.integrations.resend import ResendEmailProvider
from app.repositories.delivery_attempt import DeliveryAttemptRepository
from app.repositories.idempotency import IdempotencyRepository
from app.repositories.notification import NotificationRepository
from app.services.delivery_worker import DeliveryWorkerService
from app.services.event_processor import EventProcessorService
from app.services.notification import NotificationService
from app.services.webhook_processor import WebhookProcessorService

http_bearer = HTTPBearer(auto_error=False)


def get_tasks_dispatcher(request: Request) -> CloudTasksDispatcher:
    """Returns the shared CloudTasksDispatcher instance."""
    dispatcher = getattr(request.app.state, "tasks_dispatcher", None)
    if dispatcher is None:
        dispatcher = CloudTasksDispatcher()
    return dispatcher


def get_email_provider(request: Request) -> EmailProvider:
    """Returns the configured EmailProvider (Resend or Mock in dev/test)."""
    provider = getattr(request.app.state, "email_provider", None)
    if provider is None:
        if settings.enable_mock_delivery or not settings.resend_api_key:
            provider = MockEmailProvider()
        else:
            provider = ResendEmailProvider(http_client=getattr(request.app.state, "http_client", None))
    return provider


async def get_current_service(
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
) -> ServiceIdentity:
    """
    Dependency that verifies service-to-service JWT tokens issued by Identity Service.
    """
    if credentials is None or not credentials.credentials:
        # If in development or testing without token, return a default identity if configured
        if settings.environment == "development" and not settings.jwt_secret_key:
            return ServiceIdentity(sub="service:development", app_id="development")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer service authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return verify_service_token(credentials.credentials)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def verify_cloud_tasks_caller(
    request: Request,
    x_cloudtasks_queuename: str | None = Header(None, alias="X-CloudTasks-QueueName"),
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
) -> bool:
    """
    Validates that a task request originates from Google Cloud Tasks or an authorized internal worker.
    """
    # Cloud Tasks injects specific HTTP headers
    if x_cloudtasks_queuename:
        return True

    # Allow internal service tokens
    if credentials and credentials.credentials:
        try:
            verify_service_token(credentials.credentials)
            return True
        except Exception:
            pass

    # Allow in local development
    if settings.environment == "development":
        return True

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Unauthorized Cloud Tasks invocation",
    )


def get_notification_service(
    db: AsyncClient = Depends(get_db),
    tasks_dispatcher: CloudTasksDispatcher = Depends(get_tasks_dispatcher),
) -> NotificationService:
    return NotificationService(
        notification_repo=NotificationRepository(db),
        idempotency_repo=IdempotencyRepository(db),
        tasks_dispatcher=tasks_dispatcher,
    )


def get_event_processor_service(
    db: AsyncClient = Depends(get_db),
    tasks_dispatcher: CloudTasksDispatcher = Depends(get_tasks_dispatcher),
) -> EventProcessorService:
    return EventProcessorService(
        notification_repo=NotificationRepository(db),
        idempotency_repo=IdempotencyRepository(db),
        tasks_dispatcher=tasks_dispatcher,
    )


def get_delivery_worker_service(
    db: AsyncClient = Depends(get_db),
    email_provider: EmailProvider = Depends(get_email_provider),
) -> DeliveryWorkerService:
    return DeliveryWorkerService(
        notification_repo=NotificationRepository(db),
        attempt_repo=DeliveryAttemptRepository(db),
        email_provider=email_provider,
    )


def get_webhook_processor_service(
    db: AsyncClient = Depends(get_db),
) -> WebhookProcessorService:
    return WebhookProcessorService(
        notification_repo=NotificationRepository(db),
    )
