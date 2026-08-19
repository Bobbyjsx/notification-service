import logging
import uuid
from datetime import UTC, datetime

from app.core.errors import AuthorizationError, NotFoundError
from app.core.security import ServiceIdentity
from app.core.state_machine import NotificationStatus
from app.integrations.cloud_tasks import CloudTasksDispatcher
from app.models.notification import NotificationDB
from app.repositories.idempotency import IdempotencyRepository
from app.repositories.notification import NotificationRepository
from app.schemas.notification import NotificationCreate, NotificationResponse
from app.schemas.task import EmailDeliveryTaskPayload
from app.services.template_renderer import TemplateRenderer, template_renderer

logger = logging.getLogger(__name__)

# Service to template access control list
# Restricts which services can trigger which notification templates
SERVICE_PERMISSIONS: dict[str, list[str]] = {
    "identity-service": [
        "identity.email_verification",
        "identity.password_reset",
        "general.notification",
    ],
    "ai-service": [
        "ai.response_completed",
        "general.notification",
    ],
    "payment-service": [
        "payment.completed",
        "general.notification",
    ],
    "admin": ["*"],
}


class NotificationService:
    """Core domain service for orchestrating notification creation and delivery."""

    def __init__(
        self,
        notification_repo: NotificationRepository,
        idempotency_repo: IdempotencyRepository,
        tasks_dispatcher: CloudTasksDispatcher,
        renderer: TemplateRenderer = template_renderer,
    ) -> None:
        self.notification_repo = notification_repo
        self.idempotency_repo = idempotency_repo
        self.tasks_dispatcher = tasks_dispatcher
        self.renderer = renderer

    def authorize_service_template(self, service: ServiceIdentity, template_id: str) -> None:
        """Verifies that the calling service has permission to dispatch the requested template."""
        app_id = service.app_id
        allowed = SERVICE_PERMISSIONS.get(app_id)

        # If no specific restrictive ACL is defined for this application, allow standard templates
        if allowed is None or "*" in allowed or template_id in allowed:
            return

        raise AuthorizationError(
            f"Service '{app_id}' is not authorized to send notifications with template '{template_id}'. Allowed templates: {allowed}",
            details={"app_id": app_id, "template_id": template_id, "allowed_templates": allowed},
        )

    async def create_notification(
        self,
        service: ServiceIdentity,
        payload: NotificationCreate,
    ) -> NotificationResponse:
        """Creates a new notification record and schedules asynchronous delivery via Cloud Tasks."""
        # 1. Authorize service
        self.authorize_service_template(service, payload.template_id)

        # 2. Validate template context
        self.renderer.validate_template_context(payload.template_id, payload.template_context)

        # 3. Check client idempotency key
        if payload.idempotency_key:
            existing = await self.notification_repo.get_by_idempotency_key(service.app_id, payload.idempotency_key)
            if existing:
                logger.info(
                    "Idempotent notification hit for app %s key %s (existing id: %s)",
                    service.app_id,
                    payload.idempotency_key,
                    existing.id,
                )
                return NotificationResponse.model_validate(existing)

        # 4. Construct persistent record
        now_iso = datetime.now(UTC).isoformat()
        notification_id = f"notif_{uuid.uuid4().hex}"

        record = NotificationDB(
            id=notification_id,
            app_id=service.app_id,
            tenant_id=service.metadata.get("tenant_id"),
            channel="email",
            recipient=payload.recipient,
            template_id=payload.template_id,
            subject=payload.subject,
            status=NotificationStatus.QUEUED,
            idempotency_key=payload.idempotency_key,
            correlation_id=payload.correlation_id,
            provider="resend",
            template_context=payload.template_context,
            metadata=payload.metadata,
            created_at=now_iso,
            updated_at=now_iso,
        )

        # 5. Persist to Firestore
        await self.notification_repo.create(record)

        if payload.idempotency_key:
            composite_key = f"{service.app_id}:{payload.idempotency_key}"
            await self.idempotency_repo.record_key(
                composite_key=composite_key,
                idempotency_key=payload.idempotency_key,
                notification_id=notification_id,
                app_id=service.app_id,
                status="queued",
            )

        # 6. Enqueue delivery task to Cloud Tasks
        task_payload = EmailDeliveryTaskPayload(
            notification_id=notification_id,
            app_id=service.app_id,
            recipient=payload.recipient,
            template_id=payload.template_id,
            subject=payload.subject,
            template_context=payload.template_context,
            attempt_number=1,
            correlation_id=payload.correlation_id,
        )
        await self.tasks_dispatcher.enqueue_delivery_task(task_payload)

        return NotificationResponse.model_validate(record)

    async def get_notification(self, service: ServiceIdentity, notification_id: str) -> NotificationResponse:
        """Retrieves a notification record ensuring tenant/service ownership."""
        notification = await self.notification_repo.get_by_id(notification_id)
        if not notification:
            raise NotFoundError(f"Notification {notification_id} not found")

        # Multi-tenant ownership check
        if notification.app_id != service.app_id and service.app_id != "admin":
            raise NotFoundError(f"Notification {notification_id} not found")

        return NotificationResponse.model_validate(notification)

    async def list_notifications(
        self,
        service: ServiceIdentity,
        status: NotificationStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[NotificationResponse], int]:
        """Lists notifications scoped to the authenticated service."""
        items, total = await self.notification_repo.list_notifications(
            app_id=service.app_id,
            status=status,
            limit=limit,
            offset=offset,
        )
        responses = [NotificationResponse.model_validate(item) for item in items]
        return responses, total
