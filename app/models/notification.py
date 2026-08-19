from typing import Any

from pydantic import BaseModel, Field

from app.core.state_machine import NotificationStatus


class NotificationDB(BaseModel):
    """Persistent Firestore record for a notification."""

    id: str
    app_id: str
    tenant_id: str | None = None
    channel: str = "email"
    recipient: str
    template_id: str
    subject: str
    status: NotificationStatus = NotificationStatus.QUEUED
    event_id: str | None = None
    idempotency_key: str | None = None
    correlation_id: str | None = None
    provider: str = "resend"
    provider_message_id: str | None = None
    attempts_count: int = 0
    last_attempt_at: str | None = None
    last_error: str | None = None
    template_context: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str
    sent_at: str | None = None
    delivered_at: str | None = None
