import pytest
from httpx import AsyncClient

from tests.conftest import create_test_service_token


@pytest.mark.asyncio
async def test_create_notification_direct_api(async_client: AsyncClient):
    token = create_test_service_token(app_id="identity-service")
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "recipient": "user@example.com",
        "template_id": "identity.email_verification",
        "subject": "Verify your email",
        "template_context": {
            "otp": "654321",
            "app_name": "Auth Platform",
        },
        "idempotency_key": "idemp_test_001",
    }

    response = await async_client.post(
        "/api/v1/notifications",
        json=payload,
        headers=headers,
    )
    assert response.status_code == 202
    data = response.json()
    assert data["id"] is not None
    assert data["status"] == "queued"
    assert data["recipient"] == "user@example.com"
    notif_id = data["id"]

    # Test GET by ID
    get_resp = await async_client.get(f"/api/v1/notifications/{notif_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == notif_id

    # Test Idempotency with same key
    idemp_resp = await async_client.post(
        "/api/v1/notifications",
        json=payload,
        headers=headers,
    )
    assert idemp_resp.status_code == 202
    assert idemp_resp.json()["id"] == notif_id


@pytest.mark.asyncio
async def test_create_notification_unauthorized_service(async_client: AsyncClient):
    # ai-service trying to send identity.password_reset (not in its allowed permissions)
    token = create_test_service_token(app_id="ai-service")
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "recipient": "user@example.com",
        "template_id": "identity.password_reset",
        "subject": "Reset Password",
        "template_context": {"reset_url": "https://auth.example.com/reset"},
    }

    response = await async_client.post(
        "/api/v1/notifications",
        json=payload,
        headers=headers,
    )
    assert response.status_code == 403
    assert response.json()["error"] == "FORBIDDEN"
