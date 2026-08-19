import base64
import json

import pytest
from httpx import AsyncClient

from tests.conftest import create_test_service_token


@pytest.mark.asyncio
async def test_direct_event_ingest(async_client: AsyncClient):
    token = create_test_service_token(app_id="identity-service")
    headers = {"Authorization": f"Bearer {token}"}

    event = {
        "id": "evt_api_test_100",
        "type": "user.password_reset_requested",
        "version": 1,
        "source": "identity-service",
        "timestamp": "2026-08-19T10:00:00Z",
        "subject": "Reset your password",
        "data": {
            "email": "resetuser@example.com",
            "reset_url": "https://auth.example.com/reset?token=abc",
            "app_name": "Auth Platform",
        },
    }

    response = await async_client.post("/api/v1/events", json=event, headers=headers)
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert data["action_taken"] == "queued"
    assert data["notification_id"] is not None


@pytest.mark.asyncio
async def test_pubsub_push_ingest(async_client: AsyncClient):
    event_dict = {
        "id": "evt_pubsub_200",
        "type": "user.email_verification_requested",
        "version": 1,
        "source": "identity-service",
        "timestamp": "2026-08-19T10:00:00Z",
        "subject": "Verify your email",
        "data": {
            "email": "pubsubuser@example.com",
            "otp": "998877",
            "app_name": "Auth App",
        },
    }

    b64_data = base64.b64encode(json.dumps(event_dict).encode("utf-8")).decode("utf-8")

    envelope = {
        "message": {
            "data": b64_data,
            "messageId": "pubsub_msg_12345",
            "publishTime": "2026-08-19T10:00:00Z",
        },
        "subscription": "projects/test-project/subscriptions/notification-sub",
    }

    response = await async_client.post("/api/v1/events/pubsub", json=envelope)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "accepted"
    assert data["action_taken"] == "queued"
    assert data["event_id"] == "evt_pubsub_200"
