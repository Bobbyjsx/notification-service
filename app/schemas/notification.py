from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.state_machine import NotificationStatus


class NotificationCreate(BaseModel):
    """Schema for direct internal service-to-service notification requests."""

    recipient: EmailStr = Field(..., description="Target recipient email address")
    template_id: str = Field(..., min_length=1, max_length=128, description="Identifier of the template to render")
    subject: str = Field(..., min_length=1, max_length=256, description="Email subject line")
    template_context: dict[str, Any] = Field(default_factory=dict, description="Variables passed to template")
    idempotency_key: str | None = Field(None, max_length=256, description="Optional client idempotency key")
    correlation_id: str | None = Field(None, max_length=256, description="Distributed tracing correlation ID")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional custom metadata")


class NotificationResponse(BaseModel):
    """Public representation of a notification record."""

    id: str
    app_id: str
    tenant_id: str | None = None
    channel: str
    recipient: str
    template_id: str
    subject: str
    status: NotificationStatus
    event_id: str | None = None
    idempotency_key: str | None = None
    correlation_id: str | None = None
    provider: str
    provider_message_id: str | None = None
    attempts_count: int
    last_error: str | None = None
    created_at: str
    updated_at: str
    sent_at: str | None = None
    delivered_at: str | None = None

    model_config = ConfigDict(from_attributes=True)
