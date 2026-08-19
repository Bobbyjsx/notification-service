import pytest
from httpx import AsyncClient

from app.core.state_machine import NotificationStatus
from app.models.notification import NotificationDB
from app.repositories.notification import NotificationRepository


@pytest.mark.asyncio
async def test_cloud_tasks_worker_endpoint(async_client: AsyncClient, db):
    notif_repo = NotificationRepository(db)

    notif = NotificationDB(
        id="notif_task_api_1",
        app_id="identity-service",
        channel="email",
        recipient="taskuser@example.com",
        template_id="identity.email_verification",
        subject="Verify your email",
        status=NotificationStatus.QUEUED,
        template_context={"otp": "112233", "app_name": "Auth App"},
        created_at="2026-08-19T10:00:00Z",
        updated_at="2026-08-19T10:00:00Z",
    )
    await notif_repo.create(notif)

    payload = {
        "notification_id": "notif_task_api_1",
        "app_id": "identity-service",
        "recipient": "taskuser@example.com",
        "template_id": "identity.email_verification",
        "subject": "Verify your email",
        "template_context": {"otp": "112233", "app_name": "Auth App"},
        "attempt_number": 1,
    }

    # Cloud Tasks request with header
    headers = {"X-CloudTasks-QueueName": "notification-delivery"}
    response = await async_client.post(
        "/api/v1/tasks/deliver-email",
        json=payload,
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "sent"
    assert data["notification_id"] == "notif_task_api_1"
