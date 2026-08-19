from typing import Any

from pydantic import BaseModel, EmailStr, Field


class EmailDeliveryTaskPayload(BaseModel):
    """Payload dispatched to Cloud Tasks and consumed by the Notification Worker."""

    notification_id: str = Field(..., description="Firestore notification document ID")
    app_id: str = Field(..., description="Originating service / tenant ID")
    recipient: EmailStr = Field(..., description="Recipient email address")
    template_id: str = Field(..., description="Template identifier to render")
    subject: str = Field(..., description="Rendered or base subject line")
    template_context: dict[str, Any] = Field(default_factory=dict, description="Variables for template rendering")
    attempt_number: int = Field(default=1, ge=1, description="Current delivery attempt sequence")
    correlation_id: str | None = None


class TaskExecutionResponse(BaseModel):
    """Result returned by the Cloud Tasks worker endpoint."""

    status: str  # "sent", "already_processed", "failed_permanent", "retrying"
    notification_id: str
    provider_message_id: str | None = None
    attempt_number: int
    duration_ms: float
