import base64
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.errors import EventParsingError
from app.core.state_machine import NotificationStatus
from app.integrations.cloud_tasks import CloudTasksDispatcher
from app.models.notification import NotificationDB
from app.repositories.idempotency import IdempotencyRepository
from app.repositories.notification import NotificationRepository
from app.schemas.event import EventIngestResponse, PlatformEvent, PubSubPushEnvelope
from app.schemas.task import EmailDeliveryTaskPayload
from app.services.template_renderer import TEMPLATE_REGISTRY, TemplateRenderer, template_renderer

logger = logging.getLogger(__name__)

# Mapping from platform event types to template definitions and extractor rules
EVENT_NOTIFICATION_MAPPINGS: dict[str, dict[str, Any]] = {
    "user.email_verification_requested": {
        "template_id": "identity.email_verification",
        "subject": "Verify your email",
        "recipient_key": ["email", "recipient", "user_email"],
        "context_keys": ["otp", "app_name", "expiration_minutes"],
    },
    "user.password_reset_requested": {
        "template_id": "identity.password_reset",
        "subject": "Reset your password",
        "recipient_key": ["email", "recipient", "user_email"],
        "context_keys": ["reset_url", "app_name", "expiration_minutes"],
    },
    "payment.completed": {
        "template_id": "payment.completed",
        "subject": "Payment Confirmation",
        "recipient_key": ["customer_email", "email", "recipient"],
        "context_keys": ["amount", "currency", "receipt_id", "payment_date", "app_name"],
    },
    "ai.response.completed": {
        "template_id": "ai.response_completed",
        "subject": "AI Processing Completed",
        "recipient_key": ["user_email", "email", "recipient"],
        "context_keys": ["task_title", "summary", "result_url", "app_name"],
    },
}


class EventProcessorService:
    """Consumes and resolves platform events into asynchronous notification jobs."""

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

    def parse_pubsub_message(self, envelope: PubSubPushEnvelope) -> PlatformEvent:
        """Decodes base64 payload from GCP Pub/Sub push subscription and parses into PlatformEvent."""
        raw_data = envelope.message.data.strip()
        payload_dict: dict[str, Any] | None = None

        # 1. Try Base64 decoding (with automatic padding and urlsafe support)
        try:
            # Fix base64 padding if missing
            padding = (4 - len(raw_data) % 4) % 4
            padded_data = raw_data + ("=" * padding)
            decoded_bytes = base64.urlsafe_b64decode(padded_data)
            payload_dict = json.loads(decoded_bytes.decode("utf-8"))
        except Exception:
            payload_dict = None

        # 2. Graceful fallback: check if raw un-encoded JSON was passed in message.data
        if payload_dict is None:
            try:
                payload_dict = json.loads(raw_data)
            except Exception as exc:
                logger.warning("Failed to decode Pub/Sub message data: %s", exc)
                raise EventParsingError(
                    f"Malformed Pub/Sub message.data: Expected a base64-encoded JSON string or valid JSON object. Parsing error: {exc}",
                    details={"message_id": envelope.message.messageId, "raw_data_preview": raw_data[:100]},
                ) from exc

        try:
            return PlatformEvent(**payload_dict)
        except Exception as exc:
            raise EventParsingError(
                f"Pub/Sub decoded JSON does not conform to PlatformEvent schema: {exc}",
                details={"message_id": envelope.message.messageId, "parsed_keys": list(payload_dict.keys())},
            ) from exc

    async def process_event(self, event: PlatformEvent) -> EventIngestResponse:
        """Processes a platform event envelope idempotently."""
        event_id = event.id
        event_type = event.type
        source = event.source

        logger.info("Processing event id=%s type=%s from source=%s", event_id, event_type, source)

        # 1. Check event-level idempotency
        existing = await self.notification_repo.get_by_event_id(event_id)
        if existing:
            logger.info("Event %s was already processed as notification %s", event_id, existing.id)
            return EventIngestResponse(
                status="accepted",
                event_id=event_id,
                notification_id=existing.id,
                action_taken="duplicate",
                reason=f"Event '{event_id}' has already been processed as notification '{existing.id}'",
                details={"notification_id": existing.id, "status": str(existing.status)},
            )

        # 2. Check mapping registry
        mapping = EVENT_NOTIFICATION_MAPPINGS.get(event_type)
        if not mapping:
            supported_types = sorted(EVENT_NOTIFICATION_MAPPINGS.keys())
            logger.info("Event type '%s' has no notification mapping; ignoring", event_type)
            return EventIngestResponse(
                status="accepted",
                event_id=event_id,
                action_taken="ignored",
                reason=f"Event type '{event_type}' is not recognized. Supported types: {', '.join(supported_types)}",
                details={"event_type": event_type, "supported_event_types": supported_types},
            )

        # 3. Resolve recipient
        data = event.data
        recipient: str | None = None
        for key in mapping["recipient_key"]:
            if key in data and data[key]:
                recipient = str(data[key]).strip()
                break

        if not recipient or "@" not in recipient:
            logger.warning("Event %s missing valid recipient in payload; skipping", event_id)
            return EventIngestResponse(
                status="accepted",
                event_id=event_id,
                action_taken="ignored",
                reason=f"Missing valid recipient email in 'data'. Expected one of keys: {mapping['recipient_key']}",
                details={
                    "expected_keys": mapping["recipient_key"],
                    "provided_keys": list(data.keys()),
                },
            )

        # 4. Resolve template and context
        template_id = mapping["template_id"]
        template_context: dict[str, Any] = {}
        for key in mapping["context_keys"]:
            if key in data:
                template_context[key] = data[key]

        # Extract app_name or default to source
        if "app_name" not in template_context and "app_name" in data:
            template_context["app_name"] = data["app_name"]
            
        # Extract first_name for personalization
        if "first_name" not in template_context and "first_name" in data:
            template_context["first_name"] = data["first_name"]
            
        # Extract branding block for template customization
        if "branding" not in template_context and "branding" in data:
            template_context["branding"] = data["branding"]

        # Validate template context fields
        try:
            self.renderer.validate_template_context(template_id, template_context)
        except Exception as exc:
            template_def = TEMPLATE_REGISTRY.get(template_id, {})
            required_fields = template_def.get("required_fields", [])
            logger.warning("Event %s failed template validation: %s", event_id, exc)
            return EventIngestResponse(
                status="accepted",
                event_id=event_id,
                action_taken="ignored",
                reason=f"Template '{template_id}' validation failed: {exc}",
                details={
                    "template_id": template_id,
                    "required_fields": required_fields,
                    "provided_data_fields": list(data.keys()),
                },
            )

        # 5. Create persistent notification record
        now_iso = datetime.now(UTC).isoformat()
        notification_id = f"notif_{uuid.uuid4().hex}"
        subject = event.subject or mapping.get("default_subject", "Notification")

        record = NotificationDB(
            id=notification_id,
            app_id=source,
            tenant_id=event.metadata.tenant_id,
            channel="email",
            recipient=recipient,
            template_id=template_id,
            subject=subject,
            status=NotificationStatus.QUEUED,
            event_id=event_id,
            correlation_id=event.metadata.correlation_id,
            provider="resend",
            template_context=template_context,
            metadata={"source_event": event_type, "event_version": event.version},
            created_at=now_iso,
            updated_at=now_iso,
        )

        await self.notification_repo.create(record)

        # Record idempotency record
        await self.idempotency_repo.record_key(
            composite_key=f"event:{event_id}",
            idempotency_key=event_id,
            notification_id=notification_id,
            app_id=source,
            status="queued",
        )

        # 6. Schedule delivery task via Cloud Tasks
        task_payload = EmailDeliveryTaskPayload(
            notification_id=notification_id,
            app_id=source,
            recipient=recipient,
            template_id=template_id,
            subject=subject,
            template_context=template_context,
            attempt_number=1,
            correlation_id=event.metadata.correlation_id,
        )
        await self.tasks_dispatcher.enqueue_delivery_task(task_payload)

        return EventIngestResponse(
            status="accepted",
            event_id=event_id,
            notification_id=notification_id,
            action_taken="queued",
        )
