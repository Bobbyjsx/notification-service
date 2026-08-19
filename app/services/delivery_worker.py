import logging
import time
import uuid
from datetime import UTC, datetime

from app.core.config import settings
from app.core.errors import (
    NotFoundError,
    PermanentProviderError,
    TemplateRenderError,
    TransientProviderError,
)
from app.core.state_machine import NotificationStatus
from app.integrations.base import EmailProvider
from app.integrations.identity import get_app_branding
from app.models.delivery_attempt import DeliveryAttemptDB
from app.repositories.delivery_attempt import DeliveryAttemptRepository
from app.repositories.notification import NotificationRepository
from app.schemas.task import EmailDeliveryTaskPayload, TaskExecutionResponse
from app.services.template_renderer import TemplateRenderer, template_renderer

logger = logging.getLogger(__name__)


class DeliveryWorkerService:
    """Worker service that executes asynchronous email delivery jobs."""

    def __init__(
        self,
        notification_repo: NotificationRepository,
        attempt_repo: DeliveryAttemptRepository,
        email_provider: EmailProvider,
        renderer: TemplateRenderer = template_renderer,
    ) -> None:
        self.notification_repo = notification_repo
        self.attempt_repo = attempt_repo
        self.email_provider = email_provider
        self.renderer = renderer

    async def execute_task(self, task: EmailDeliveryTaskPayload) -> TaskExecutionResponse:
        """
        Executes a delivery task with idempotency checks, atomic transitions,
        and failure classification.
        """
        notification_id = task.notification_id
        attempt_num = task.attempt_number
        start_time = time.perf_counter()

        logger.info(
            "Worker starting delivery task for notification %s (attempt %d)",
            notification_id,
            attempt_num,
        )

        # 1. Load notification record
        notification = await self.notification_repo.get_by_id(notification_id)
        if not notification:
            logger.error("Notification %s not found in Firestore", notification_id)
            raise NotFoundError(f"Notification {notification_id} not found")

        # 2. Idempotency Check: if already sent or delivered, return without duplicate send
        if notification.status in {
            NotificationStatus.SENT,
            NotificationStatus.DELIVERED,
            NotificationStatus.BOUNCED,
            NotificationStatus.COMPLAINED,
        }:
            logger.info(
                "Notification %s is already in terminal/sent state '%s'; skipping duplicate delivery",
                notification_id,
                notification.status.value,
            )
            duration_ms = (time.perf_counter() - start_time) * 1000
            return TaskExecutionResponse(
                status="already_processed",
                notification_id=notification_id,
                provider_message_id=notification.provider_message_id,
                attempt_number=attempt_num,
                duration_ms=duration_ms,
            )

        # 3. Transition to processing
        try:
            await self.notification_repo.atomic_transition_status(
                notification_id=notification_id,
                target_status=NotificationStatus.PROCESSING,
                expected_current_statuses=[NotificationStatus.QUEUED, NotificationStatus.PROCESSING],
            )
        except Exception as exc:
            logger.warning("Could not transition notification %s to processing: %s", notification_id, exc)

        # 3.5. Fetch dynamic application branding from Identity Service
        if task.app_id:
            brand_config = await get_app_branding(task.app_id)
            if brand_config:
                # Merge fetched branding into template context without overwriting explicit event data
                if "app_name" not in task.template_context and "app_name" in brand_config:
                    task.template_context["app_name"] = brand_config["app_name"]
                
                if "branding" not in task.template_context and "branding" in brand_config:
                    # Filter out None values to let templates fall back to defaults gracefully
                    clean_branding = {k: v for k, v in brand_config["branding"].items() if v is not None}
                    task.template_context["branding"] = clean_branding

        # 4. Render Email Template
        try:
            resolved_subject, html_body, text_body = self.renderer.render(
                template_id=task.template_id,
                context=task.template_context,
                subject=task.subject,
            )
        except TemplateRenderError as exc:
            logger.error("Permanent template render error for %s: %s", notification_id, exc)
            duration_ms = (time.perf_counter() - start_time) * 1000
            await self._record_attempt(
                notification_id=notification_id,
                attempt_num=attempt_num,
                status="failed",
                error_code=exc.code,
                error_msg=str(exc),
                is_transient=False,
                duration_ms=duration_ms,
            )
            await self.notification_repo.atomic_transition_status(
                notification_id=notification_id,
                target_status=NotificationStatus.FAILED,
                last_error=str(exc),
            )
            return TaskExecutionResponse(
                status="failed_permanent",
                notification_id=notification_id,
                attempt_number=attempt_num,
                duration_ms=duration_ms,
            )

        # 5. Invoke Email Provider
        try:
            app_name = task.template_context.get("app_name", "Platform")
            default_email = settings.default_from_email
            from_email = f"{app_name} <{default_email}>"
            
            result = await self.email_provider.send_email(
                to=task.recipient,
                subject=resolved_subject,
                html_body=html_body,
                text_body=text_body,
                from_email=from_email,
            )

            duration_ms = (time.perf_counter() - start_time) * 1000

            # 6. Record success attempt and update status to sent
            await self._record_attempt(
                notification_id=notification_id,
                attempt_num=attempt_num,
                status="sent",
                provider_response_id=result.message_id,
                duration_ms=duration_ms,
            )

            await self.notification_repo.atomic_transition_status(
                notification_id=notification_id,
                target_status=NotificationStatus.SENT,
                provider_message_id=result.message_id,
            )

            logger.info("Successfully delivered notification %s (provider id: %s)", notification_id, result.message_id)

            return TaskExecutionResponse(
                status="sent",
                notification_id=notification_id,
                provider_message_id=result.message_id,
                attempt_number=attempt_num,
                duration_ms=duration_ms,
            )

        except PermanentProviderError as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error("Permanent provider failure delivering %s: %s", notification_id, exc)

            await self._record_attempt(
                notification_id=notification_id,
                attempt_num=attempt_num,
                status="failed",
                error_code=exc.code,
                error_msg=str(exc),
                is_transient=False,
                duration_ms=duration_ms,
            )

            await self.notification_repo.atomic_transition_status(
                notification_id=notification_id,
                target_status=NotificationStatus.FAILED,
                last_error=str(exc),
            )

            # Return permanent failure (200 status code for Cloud Tasks so it drops from queue)
            return TaskExecutionResponse(
                status="failed_permanent",
                notification_id=notification_id,
                attempt_number=attempt_num,
                duration_ms=duration_ms,
            )

        except TransientProviderError as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.warning(
                "Transient provider failure delivering %s (attempt %d): %s", notification_id, attempt_num, exc
            )

            await self._record_attempt(
                notification_id=notification_id,
                attempt_num=attempt_num,
                status="failed",
                error_code=exc.code,
                error_msg=str(exc),
                is_transient=True,
                duration_ms=duration_ms,
            )

            await self.notification_repo.increment_attempt(
                notification_id=notification_id,
                last_error=str(exc),
            )

            # Check if retry limit exceeded
            if attempt_num >= settings.max_delivery_attempts:
                logger.error("Notification %s exhausted maximum retry attempts (%d)", notification_id, attempt_num)
                await self.notification_repo.atomic_transition_status(
                    notification_id=notification_id,
                    target_status=NotificationStatus.FAILED,
                    last_error=f"Exhausted retries: {exc}",
                )
                return TaskExecutionResponse(
                    status="failed_exhausted",
                    notification_id=notification_id,
                    attempt_number=attempt_num,
                    duration_ms=duration_ms,
                )

            # Re-queue for next attempt and re-raise so Cloud Tasks returns 5xx and retries
            await self.notification_repo.atomic_transition_status(
                notification_id=notification_id,
                target_status=NotificationStatus.QUEUED,
            )
            raise

    async def _record_attempt(
        self,
        notification_id: str,
        attempt_num: int,
        status: str,
        provider_response_id: str | None = None,
        error_code: str | None = None,
        error_msg: str | None = None,
        is_transient: bool = False,
        duration_ms: float = 0.0,
    ) -> None:
        now_iso = datetime.now(UTC).isoformat()
        attempt = DeliveryAttemptDB(
            id=f"att_{uuid.uuid4().hex}",
            notification_id=notification_id,
            attempt_number=attempt_num,
            provider="resend",
            status=status,
            provider_response_id=provider_response_id,
            error_code=error_code,
            error_message=error_msg,
            is_transient=is_transient,
            duration_ms=duration_ms,
            created_at=now_iso,
        )
        try:
            await self.attempt_repo.create(attempt)
        except Exception as exc:
            logger.warning("Failed to record delivery attempt in Firestore: %s", exc)
