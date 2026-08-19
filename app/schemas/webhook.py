from typing import Any

from pydantic import BaseModel, Field


class ResendWebhookData(BaseModel):
    """Payload data embedded in a Resend webhook event."""

    id: str | None = None
    email_id: str | None = None
    from_: str | None = Field(None, alias="from")
    to: list[str] | str | None = None
    subject: str | None = None
    created_at: str | None = None
    status: str | None = None
    error: dict[str, Any] | str | None = None


class ResendWebhookEvent(BaseModel):
    """Structure of an incoming webhook event from Resend."""

    type: str = Field(..., description="Event type, e.g. email.sent, email.delivered, email.bounced")
    created_at: str
    data: ResendWebhookData


class WebhookProcessResponse(BaseModel):
    """Response returned to Resend upon webhook ingestion."""

    status: str = "ok"
    event_type: str
    notification_id: str | None = None
    updated_status: str | None = None
    action_taken: str = "processed"  # "processed", "ignored", "no_matching_notification"
