from typing import Any

from pydantic import BaseModel, Field


class EventMetadata(BaseModel):
    """Standard metadata block attached to platform events."""

    correlation_id: str | None = None
    tenant_id: str | None = None
    user_id: str | None = None


class PlatformEvent(BaseModel):
    """Platform event envelope distributed via Pub/Sub or direct ingest."""

    id: str = Field(..., min_length=1, description="Globally unique event ID")
    type: str = Field(..., min_length=1, description="Event type (e.g. user.email_verification_requested)")
    version: int = Field(default=1, description="Event schema version")
    source: str = Field(..., min_length=1, description="Originating service name")
    timestamp: str = Field(..., description="ISO UTC timestamp when event was published")
    subject: str | None = Field(None, description="Event subject or identifier")
    data: dict[str, Any] = Field(default_factory=dict, description="Event payload data")
    metadata: EventMetadata = Field(default_factory=EventMetadata)


class PubSubMessage(BaseModel):
    """GCP Pub/Sub message structure."""

    data: str = Field(..., description="Base64 encoded event data")
    messageId: str = Field(..., description="GCP Pub/Sub message ID")
    publishTime: str = Field(..., description="GCP Pub/Sub publish timestamp")
    attributes: dict[str, str] = Field(default_factory=dict)


class PubSubPushEnvelope(BaseModel):
    """GCP Pub/Sub push subscription HTTP body."""

    message: PubSubMessage
    subscription: str


class EventIngestResponse(BaseModel):
    """Response returned when an event is accepted for notification processing."""

    status: str = "accepted"
    event_id: str
    notification_id: str | None = None
    action_taken: str = "queued"  # "queued", "ignored", "duplicate"
    reason: str | None = None
    details: dict[str, Any] | None = None
