"""External provider integrations package."""

from app.integrations.base import EmailProvider, EmailSendResult
from app.integrations.cloud_tasks import CloudTasksDispatcher
from app.integrations.mock import MockEmailProvider
from app.integrations.resend import ResendEmailProvider

__all__ = [
    "EmailProvider",
    "EmailSendResult",
    "ResendEmailProvider",
    "MockEmailProvider",
    "CloudTasksDispatcher",
]
