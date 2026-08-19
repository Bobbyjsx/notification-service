import logging

from app.core.errors import InvalidStateTransitionError
from app.core.state_machine import NotificationStatus
from app.repositories.notification import NotificationRepository
from app.schemas.webhook import ResendWebhookEvent, WebhookProcessResponse

logger = logging.getLogger(__name__)

# Map Resend webhook event types to internal NotificationStatus
RESEND_EVENT_STATUS_MAP: dict[str, NotificationStatus] = {
    "email.sent": NotificationStatus.SENT,
    "email.delivered": NotificationStatus.DELIVERED,
    "email.bounced": NotificationStatus.BOUNCED,
    "email.complained": NotificationStatus.COMPLAINED,
    "email.delivery_delayed": NotificationStatus.PROCESSING,
}


class WebhookProcessorService:
    """Processes incoming Resend delivery status webhooks."""

    def __init__(self, notification_repo: NotificationRepository) -> None:
        self.notification_repo = notification_repo

    async def process_webhook_event(self, event: ResendWebhookEvent) -> WebhookProcessResponse:
        """
        Processes a single Resend webhook event idempotently, updating Firestore state
        while enforcing state machine invariants.
        """
        event_type = event.type
        data = event.data

        # Resend provides message ID in data.email_id or data.id
        provider_message_id = data.email_id or data.id
        if not provider_message_id:
            logger.warning("Webhook event %s missing email_id/id in payload", event_type)
            return WebhookProcessResponse(
                status="ok",
                event_type=event_type,
                action_taken="ignored",
            )

        target_status = RESEND_EVENT_STATUS_MAP.get(event_type)
        if not target_status:
            logger.info("Ignoring untracked Resend event type: %s", event_type)
            return WebhookProcessResponse(
                status="ok",
                event_type=event_type,
                action_taken="ignored",
            )

        # 1. Lookup matching notification by provider message ID
        notification = await self.notification_repo.get_by_provider_message_id(provider_message_id)
        if not notification:
            logger.warning(
                "No notification found matching provider_message_id: %s",
                provider_message_id,
            )
            return WebhookProcessResponse(
                status="ok",
                event_type=event_type,
                action_taken="no_matching_notification",
            )

        notification_id = notification.id
        current_status = notification.status

        # 2. If already in target status, idempotent return
        if current_status == target_status:
            logger.info(
                "Notification %s is already in target status '%s'; ignoring duplicate webhook",
                notification_id,
                target_status.value,
            )
            return WebhookProcessResponse(
                status="ok",
                event_type=event_type,
                notification_id=notification_id,
                updated_status=target_status.value,
                action_taken="processed",
            )

        # 3. Apply state transition
        try:
            extra_updates = {}
            if event_type == "email.bounced" and data.error:
                extra_updates["last_error"] = str(data.error)

            await self.notification_repo.atomic_transition_status(
                notification_id=notification_id,
                target_status=target_status,
                **extra_updates,
            )
            logger.info(
                "Updated notification %s status from '%s' to '%s' via webhook",
                notification_id,
                current_status.value,
                target_status.value,
            )
            return WebhookProcessResponse(
                status="ok",
                event_type=event_type,
                notification_id=notification_id,
                updated_status=target_status.value,
                action_taken="processed",
            )
        except InvalidStateTransitionError as exc:
            logger.warning(
                "Ignoring out-of-order webhook transition for %s: %s",
                notification_id,
                exc,
            )
            return WebhookProcessResponse(
                status="ok",
                event_type=event_type,
                notification_id=notification_id,
                updated_status=current_status.value,
                action_taken="ignored",
            )
