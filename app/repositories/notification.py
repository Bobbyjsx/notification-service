import asyncio
from datetime import UTC, datetime
from typing import Any

from google.api_core.exceptions import Aborted
from google.cloud.firestore_v1.async_client import AsyncClient
from google.cloud.firestore_v1.async_transaction import AsyncTransaction, async_transactional
from google.cloud.firestore_v1.base_query import FieldFilter

from app.core.errors import InvalidStateTransitionError, NotFoundError
from app.core.state_machine import NotificationStatus, assert_valid_transition
from app.models.notification import NotificationDB
from app.repositories.base import BaseRepository


@async_transactional
async def _transition_in_transaction(
    tx: AsyncTransaction,
    collection: Any,
    notification_id: str,
    target_status: NotificationStatus,
    expected_current_statuses: list[NotificationStatus] | None,
    additional_updates: dict[str, Any],
) -> NotificationDB:
    doc_ref = collection.document(notification_id)
    doc = await doc_ref.get(transaction=tx)
    if not doc.exists:
        raise NotFoundError(f"Notification {notification_id} does not exist")

    data = doc.to_dict() or {}
    data["id"] = doc.id
    current_notification = NotificationDB(**data)

    current_status = current_notification.status

    # If already in the target status, return current (idempotent)
    if current_status == target_status:
        return current_notification

    # Validate against explicit expected status preconditions if provided
    if expected_current_statuses and current_status not in expected_current_statuses:
        raise InvalidStateTransitionError(
            current_status=current_status.value,
            target_status=target_status.value,
            details={
                "notification_id": notification_id,
                "expected_statuses": [s.value for s in expected_current_statuses],
            },
        )

    # Validate state machine rules
    assert_valid_transition(current_status, target_status)

    now_iso = datetime.now(UTC).isoformat()
    updates: dict[str, Any] = {
        "status": target_status.value,
        "updated_at": now_iso,
        **additional_updates,
    }

    if target_status == NotificationStatus.SENT and not current_notification.sent_at:
        updates["sent_at"] = now_iso
    elif target_status == NotificationStatus.DELIVERED and not current_notification.delivered_at:
        updates["delivered_at"] = now_iso

    tx.update(doc_ref, updates)

    data.update(updates)
    return NotificationDB(**data)


class NotificationRepository(BaseRepository[NotificationDB]):
    """Firestore repository for notification records."""

    def __init__(self, db: AsyncClient) -> None:
        super().__init__(db, "notifications", NotificationDB)

    async def get_by_event_id(self, event_id: str) -> NotificationDB | None:
        """Find notification created from a specific platform event ID."""
        return await self.find_one_by_field("event_id", event_id)

    async def get_by_idempotency_key(self, app_id: str, idempotency_key: str) -> NotificationDB | None:
        """Find notification matching an app-scoped idempotency key."""
        query = (
            self.collection.where(filter=FieldFilter("app_id", "==", app_id))
            .where(filter=FieldFilter("idempotency_key", "==", idempotency_key))
            .limit(1)
        )
        docs = query.stream()
        async for doc in docs:
            data = doc.to_dict() or {}
            data["id"] = doc.id
            return NotificationDB(**data)
        return None

    async def get_by_provider_message_id(self, provider_message_id: str) -> NotificationDB | None:
        """Find notification by its Resend message ID."""
        return await self.find_one_by_field("provider_message_id", provider_message_id)

    async def atomic_transition_status(
        self,
        notification_id: str,
        target_status: NotificationStatus,
        expected_current_statuses: list[NotificationStatus] | None = None,
        **additional_updates: Any,
    ) -> NotificationDB:
        """
        Executes a transactional status transition with state machine validation
        and optimistic concurrency checking.
        """
        for attempt in range(3):
            try:
                return await _transition_in_transaction(
                    self.db.transaction(),
                    self.collection,
                    notification_id,
                    target_status,
                    expected_current_statuses,
                    additional_updates,
                )
            except (InvalidStateTransitionError, NotFoundError):
                raise
            except (Aborted, ValueError):
                if attempt == 2:
                    raise
                await asyncio.sleep(0.05 * (attempt + 1))

        raise RuntimeError(f"Failed to transition status for notification {notification_id}")

    async def increment_attempt(
        self,
        notification_id: str,
        last_error: str | None = None,
    ) -> NotificationDB:
        """Increment attempt counter and record last error string."""
        now_iso = datetime.now(UTC).isoformat()
        notification = await self.get_by_id(notification_id)
        if not notification:
            raise NotFoundError(f"Notification {notification_id} not found")

        attempts = notification.attempts_count + 1
        updates: dict[str, Any] = {
            "attempts_count": attempts,
            "last_attempt_at": now_iso,
            "updated_at": now_iso,
        }
        if last_error:
            updates["last_error"] = last_error

        await self.update(notification_id, updates)
        notification.attempts_count = attempts
        notification.last_attempt_at = now_iso
        notification.last_error = last_error
        notification.updated_at = now_iso
        return notification

    async def list_notifications(
        self,
        app_id: str,
        status: NotificationStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[NotificationDB], int]:
        """Queries notifications by app and status with offset/limit pagination."""
        query = self.collection.where(filter=FieldFilter("app_id", "==", app_id))
        if status:
            query = query.where(filter=FieldFilter("status", "==", status.value))

        # Stream documents
        items: list[NotificationDB] = []
        stream = query.stream()
        all_docs = []
        async for doc in stream:
            all_docs.append(doc)

        total = len(all_docs)
        # Sort in memory by created_at desc if needed
        all_docs.sort(key=lambda d: d.to_dict().get("created_at", ""), reverse=True)
        paged_docs = all_docs[offset : offset + limit]

        for doc in paged_docs:
            data = doc.to_dict() or {}
            data["id"] = doc.id
            items.append(NotificationDB(**data))

        return items, total
