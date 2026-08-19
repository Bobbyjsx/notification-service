from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EmailSendResult:
    """Standardized response from any email provider implementation."""

    provider: str
    message_id: str
    recipient: str
    raw_response: dict[str, Any] = field(default_factory=dict)


class EmailProvider(ABC):
    """Abstract interface defining required email delivery capabilities."""

    @abstractmethod
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
        """Delivers an email message through the provider."""
        pass
