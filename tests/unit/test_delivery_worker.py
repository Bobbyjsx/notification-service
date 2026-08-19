import pytest

from app.core.state_machine import NotificationStatus
from app.integrations.mock import MockEmailProvider
from app.models.notification import NotificationDB
from app.repositories.delivery_attempt import DeliveryAttemptRepository
from app.repositories.notification import NotificationRepository
from app.schemas.task import EmailDeliveryTaskPayload
from app.services.delivery_worker import DeliveryWorkerService


@pytest.mark.asyncio
async def test_delivery_worker_success(db):
    notif_repo = NotificationRepository(db)
    attempt_repo = DeliveryAttemptRepository(db)
    provider = MockEmailProvider()
    worker = DeliveryWorkerService(notif_repo, attempt_repo, provider)

    # 1. Create a queued notification in Firestore
    notif = NotificationDB(
        id="notif_test_worker_1",
        app_id="identity-service",
        channel="email",
        recipient="recipient@example.com",
        template_id="identity.email_verification",
        subject="Verify your email",
        status=NotificationStatus.QUEUED,
        template_context={"otp": "123456", "app_name": "Auth App"},
        created_at="2026-08-19T10:00:00Z",
        updated_at="2026-08-19T10:00:00Z",
    )
    await notif_repo.create(notif)

    # 2. Execute worker task
    task = EmailDeliveryTaskPayload(
        notification_id="notif_test_worker_1",
        app_id="identity-service",
        recipient="recipient@example.com",
        template_id="identity.email_verification",
        subject="Verify your email",
        template_context={"otp": "123456", "app_name": "Auth App"},
        attempt_number=1,
    )
    response = await worker.execute_task(task)

    assert response.status == "sent"
    assert response.provider_message_id is not None
    assert len(provider.sent_emails) == 1

    # Verify Firestore record was updated to SENT
    updated_notif = await notif_repo.get_by_id("notif_test_worker_1")
    assert updated_notif.status == NotificationStatus.SENT
    assert updated_notif.provider_message_id == response.provider_message_id
    assert updated_notif.sent_at is not None

    # Verify delivery attempt log
    attempts = await attempt_repo.list_by_notification_id("notif_test_worker_1")
    assert len(attempts) == 1
    assert attempts[0].status == "sent"

    # 3. Idempotency test: re-executing task on already SENT notification returns already_processed without re-sending
    response2 = await worker.execute_task(task)
    assert response2.status == "already_processed"
    assert len(provider.sent_emails) == 1  # No duplicate send


@pytest.mark.asyncio
async def test_delivery_worker_permanent_failure(db):
    notif_repo = NotificationRepository(db)
    attempt_repo = DeliveryAttemptRepository(db)
    provider = MockEmailProvider()
    provider.simulate_permanent_error = True
    worker = DeliveryWorkerService(notif_repo, attempt_repo, provider)

    notif = NotificationDB(
        id="notif_test_worker_perm",
        app_id="identity-service",
        channel="email",
        recipient="invalid@example.com",
        template_id="identity.email_verification",
        subject="Verify",
        status=NotificationStatus.QUEUED,
        template_context={"otp": "123456"},
        created_at="2026-08-19T10:00:00Z",
        updated_at="2026-08-19T10:00:00Z",
    )
    await notif_repo.create(notif)

    task = EmailDeliveryTaskPayload(
        notification_id="notif_test_worker_perm",
        app_id="identity-service",
        recipient="invalid@example.com",
        template_id="identity.email_verification",
        subject="Verify",
        template_context={"otp": "123456"},
        attempt_number=1,
    )
    response = await worker.execute_task(task)
    assert response.status == "failed_permanent"

    updated_notif = await notif_repo.get_by_id("notif_test_worker_perm")
    assert updated_notif.status == NotificationStatus.FAILED
