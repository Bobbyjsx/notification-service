import pytest

from app.integrations.cloud_tasks import CloudTasksDispatcher
from app.repositories.idempotency import IdempotencyRepository
from app.repositories.notification import NotificationRepository
from app.schemas.event import PlatformEvent
from app.services.event_processor import EventProcessorService


@pytest.mark.asyncio
async def test_process_email_verification_event(db):
    notif_repo = NotificationRepository(db)
    idemp_repo = IdempotencyRepository(db)
    dispatcher = CloudTasksDispatcher()
    service = EventProcessorService(notif_repo, idemp_repo, dispatcher)

    event = PlatformEvent(
        id="evt_verif_001",
        type="user.email_verification_requested",
        version=1,
        source="identity-service",
        timestamp="2026-08-19T10:00:00Z",
        subject="Verify your email",
        data={
            "email": "testuser@example.com",
            "otp": "492019",
            "app_name": "Auth Platform",
        },
    )

    res = await service.process_event(event)
    assert res.status == "accepted"
    assert res.action_taken == "queued"
    assert res.notification_id is not None

    # Verify persistent notification in Firestore
    notif = await notif_repo.get_by_id(res.notification_id)
    assert notif is not None
    assert notif.recipient == "testuser@example.com"
    assert notif.template_id == "identity.email_verification"
    assert notif.status == "queued"
    assert notif.event_id == "evt_verif_001"

    # Test Idempotency: second ingest of same event ID returns duplicate without creating another record
    res2 = await service.process_event(event)
    assert res2.action_taken == "duplicate"
    assert res2.notification_id == res.notification_id


@pytest.mark.asyncio
async def test_process_unmapped_event_ignored(db):
    notif_repo = NotificationRepository(db)
    idemp_repo = IdempotencyRepository(db)
    dispatcher = CloudTasksDispatcher()
    service = EventProcessorService(notif_repo, idemp_repo, dispatcher)

    event = PlatformEvent(
        id="evt_audit_001",
        type="audit.log.created",
        version=1,
        source="audit-service",
        timestamp="2026-08-19T10:00:00Z",
        data={"action": "login"},
    )

    res = await service.process_event(event)
    assert res.status == "accepted"
    assert res.action_taken == "ignored"
    assert res.notification_id is None
