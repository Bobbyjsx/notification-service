from typing import Any

from pydantic import BaseModel, Field


class DeliveryAttemptDB(BaseModel):
    """Persistent audit log of an individual email delivery attempt."""

    id: str
    notification_id: str
    attempt_number: int
    provider: str = "resend"
    status: str
    provider_response_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    is_transient: bool = False
    duration_ms: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
