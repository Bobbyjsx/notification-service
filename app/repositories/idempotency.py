from datetime import UTC, datetime

from google.cloud.firestore_v1.async_client import AsyncClient

from app.models.idempotency import IdempotencyRecordDB
from app.repositories.base import BaseRepository


class IdempotencyRepository(BaseRepository[IdempotencyRecordDB]):
    """Firestore repository for enforcing once-and-only-once operations."""

    def __init__(self, db: AsyncClient) -> None:
        super().__init__(db, "idempotency_keys", IdempotencyRecordDB)

    async def get_by_key(self, composite_key: str) -> IdempotencyRecordDB | None:
        """Retrieves existing idempotency record by key."""
        return await self.get_by_id(composite_key)

    async def record_key(
        self,
        composite_key: str,
        idempotency_key: str,
        notification_id: str,
        app_id: str,
        status: str = "accepted",
        expires_at: str | None = None,
    ) -> IdempotencyRecordDB:
        """Records an idempotency key."""
        now_iso = datetime.now(UTC).isoformat()
        record = IdempotencyRecordDB(
            id=composite_key,
            idempotency_key=idempotency_key,
            notification_id=notification_id,
            app_id=app_id,
            status=status,
            created_at=now_iso,
            expires_at=expires_at,
        )
        return await self.create(record)
