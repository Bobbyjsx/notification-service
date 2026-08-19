import logging
import uuid

from app.integrations.base import EmailProvider, EmailSendResult

logger = logging.getLogger(__name__)


class MockEmailProvider(EmailProvider):
    """Mock in-memory provider used in tests and local development."""

    def __init__(self) -> None:
        self.sent_emails: list[dict] = []
        self.simulate_transient_error: bool = False
        self.simulate_permanent_error: bool = False

    async def send_email(
        self,
        *,
        to: str,
        subject: str,
        html_body: str,
        text_body: str | None = None,
        from_email: str | None = None,
        reply_to: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> EmailSendResult:
        from app.core.errors import PermanentProviderError, TransientProviderError

        if self.simulate_transient_error:
            raise TransientProviderError("Simulated transient network outage (503)")

        if self.simulate_permanent_error:
            raise PermanentProviderError("Simulated permanent invalid recipient (422)")

        msg_id = f"mock_msg_{uuid.uuid4().hex[:16]}"
        record = {
            "id": msg_id,
            "to": to,
            "subject": subject,
            "html_body": html_body,
            "text_body": text_body,
            "from_email": from_email,
            "headers": headers,
        }
        self.sent_emails.append(record)
        logger.info("MockEmailProvider: Simulated email delivery to %s (subject: %s, id: %s)", to, subject, msg_id)
        return EmailSendResult(
            provider="mock",
            message_id=msg_id,
            recipient=to,
            raw_response={"id": msg_id, "status": "mock_sent"},
        )
