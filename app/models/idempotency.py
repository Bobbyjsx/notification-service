from pydantic import BaseModel


class IdempotencyRecordDB(BaseModel):
    """Persistent record to enforce at-most-once processing across asynchronous events."""

    id: str  # e.g., app_id:idempotency_key or event_id
    idempotency_key: str
    notification_id: str
    app_id: str
    status: str
    created_at: str
    expires_at: str | None = None
