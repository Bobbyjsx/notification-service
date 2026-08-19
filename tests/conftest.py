import os
import time

# Set environment variables for the Firestore emulator and test runner
os.environ["FIRESTORE_EMULATOR_HOST"] = "127.0.0.1:8080"
os.environ["GOOGLE_CLOUD_PROJECT"] = "test-project"
os.environ["FIRESTORE_DATABASE"] = "(default)"
os.environ["ENVIRONMENT"] = "development"
os.environ["ENABLE_MOCK_DELIVERY"] = "true"
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-key-12345678901234567890"
os.environ["IDENTITY_ISSUER"] = "http://localhost:8002"
os.environ["IDENTITY_AUDIENCE"] = "notification-service"
os.environ["RESEND_WEBHOOK_SECRET"] = "whsec_dGVzdHNlY3JldDEyMzQ1Njc4OTA="

import httpx
import jwt
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.database import get_db_client
from app.main import app


def create_test_service_token(
    app_id: str = "identity-service",
    audience: str = "notification-service",
    issuer: str = "http://localhost:8002",
    token_type: str = "service",
    expires_in_seconds: int = 3600,
) -> str:
    """Generates a valid HMAC-signed service token for testing."""
    now = int(time.time())
    payload = {
        "iss": issuer,
        "sub": f"service:{app_id}",
        "aud": audience,
        "app_id": app_id,
        "type": token_type,
        "iat": now,
        "exp": now + expires_in_seconds,
        "jti": f"test_jti_{now}",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")


@pytest.fixture(autouse=True)
def clean_firestore_db():
    """Wipe the Firestore emulator database via its REST API between tests."""
    try:
        httpx.delete(
            "http://127.0.0.1:8080/emulator/v1/projects/test-project/databases/(default)/documents",
            timeout=2.0,
        )
    except httpx.RequestError:
        pass
    yield


@pytest_asyncio.fixture
async def db():
    """Direct Firestore emulator AsyncClient."""
    client = get_db_client()
    yield client
    client.close()


@pytest_asyncio.fixture
async def async_client():
    """Provides an ASGI test client with lifespan startup and shutdown."""
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
