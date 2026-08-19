import base64
import hashlib
import hmac
import json
import time

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.core.state_machine import NotificationStatus
from app.models.notification import NotificationDB
from app.repositories.notification import NotificationRepository


@pytest.mark.asyncio
async def test_resend_webhook_delivered(async_client: AsyncClient, db):
    notif_repo = NotificationRepository(db)

    # 1. Create a notification in SENT state with a known provider_message_id
    notif = NotificationDB(
        id="notif_webhook_test_1",
        app_id="identity-service",
        channel="email",
        recipient="delivered@example.com",
        template_id="identity.email_verification",
        subject="Verify",
        status=NotificationStatus.SENT,
        provider_message_id="msg_resend_deliv_999",
        created_at="2026-08-19T10:00:00Z",
        updated_at="2026-08-19T10:00:00Z",
    )
    await notif_repo.create(notif)

    # 2. Build signed Resend webhook payload
    webhook_body = {
        "type": "email.delivered",
        "created_at": "2026-08-19T10:05:00Z",
        "data": {
            "email_id": "msg_resend_deliv_999",
            "to": ["delivered@example.com"],
            "subject": "Verify",
        },
    }
    body_bytes = json.dumps(webhook_body).encode("utf-8")

    svix_id = "msg_svix_req_1"
    svix_timestamp = str(int(time.time()))
    raw_secret = settings.resend_webhook_secret.removeprefix("whsec_")
    secret_bytes = base64.b64decode(raw_secret)
    to_sign = f"{svix_id}.{svix_timestamp}.".encode() + body_bytes
    sig = hmac.new(secret_bytes, to_sign, hashlib.sha256).digest()
    svix_signature = f"v1,{base64.b64encode(sig).decode('utf-8')}"

    headers = {
        "Content-Type": "application/json",
        "svix-id": svix_id,
        "svix-timestamp": svix_timestamp,
        "svix-signature": svix_signature,
    }

    response = await async_client.post("/api/v1/webhooks/resend", content=body_bytes, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["action_taken"] == "processed"
    assert data["updated_status"] == "delivered"

    # Verify Firestore record was updated to DELIVERED
    updated_notif = await notif_repo.get_by_id("notif_webhook_test_1")
    assert updated_notif.status == NotificationStatus.DELIVERED
    assert updated_notif.delivered_at is not None
