from google.cloud.firestore_v1.async_client import AsyncClient
from google.cloud.firestore_v1.base_query import FieldFilter

from app.models.delivery_attempt import DeliveryAttemptDB
from app.repositories.base import BaseRepository


class DeliveryAttemptRepository(BaseRepository[DeliveryAttemptDB]):
    """Firestore repository for logging delivery attempts."""

    def __init__(self, db: AsyncClient) -> None:
        super().__init__(db, "delivery_attempts", DeliveryAttemptDB)

    async def list_by_notification_id(self, notification_id: str) -> list[DeliveryAttemptDB]:
        """Lists all delivery attempt records for a given notification ID."""
        query = self.collection.where(filter=FieldFilter("notification_id", "==", notification_id))
        docs = query.stream()
        items: list[DeliveryAttemptDB] = []
        async for doc in docs:
            data = doc.to_dict() or {}
            data["id"] = doc.id
            items.append(DeliveryAttemptDB(**data))

        # Sort by attempt number
        items.sort(key=lambda x: x.attempt_number)
        return items
