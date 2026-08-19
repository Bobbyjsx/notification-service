import base64
import hashlib
import hmac
import time

import pytest

from app.core.errors import AuthenticationError, WebhookVerificationError
from app.core.security import verify_resend_webhook_signature, verify_service_token
from tests.conftest import create_test_service_token


def test_verify_service_token_valid():
    token = create_test_service_token(app_id="identity-service")
    identity = verify_service_token(token)
    assert identity.app_id == "identity-service"
    assert identity.sub == "service:identity-service"


def test_verify_service_token_expired():
    token = create_test_service_token(app_id="identity-service", expires_in_seconds=-10)
    with pytest.raises(AuthenticationError) as exc_info:
        verify_service_token(token)
    assert "expired" in str(exc_info.value).lower()


def test_verify_service_token_audience_mismatch():
    token = create_test_service_token(audience="wrong-audience")
    with pytest.raises(AuthenticationError):
        verify_service_token(token)


def test_verify_resend_webhook_signature():
    secret = "whsec_dGVzdHNlY3JldDEyMzQ1Njc4OTA="
    raw_secret = secret.replace("whsec_", "")
    secret_bytes = base64.b64decode(raw_secret)
    body_bytes = b'{"type": "email.delivered", "data": {"email_id": "msg_123"}}'
    svix_id = "msg_svix_id_999"
    svix_timestamp = str(int(time.time()))

    to_sign = f"{svix_id}.{svix_timestamp}.".encode() + body_bytes
    sig = hmac.new(secret_bytes, to_sign, hashlib.sha256).digest()
    sig_b64 = base64.b64encode(sig).decode("utf-8")
    svix_signature = f"v1,{sig_b64}"

    verified = verify_resend_webhook_signature(
        payload_body=body_bytes,
        svix_id=svix_id,
        svix_timestamp=svix_timestamp,
        svix_signature=svix_signature,
    )
    assert verified is True


def test_verify_resend_webhook_signature_invalid():
    body_bytes = b'{"type": "email.delivered"}'
    with pytest.raises(WebhookVerificationError):
        verify_resend_webhook_signature(
            payload_body=body_bytes,
            svix_id="svix_1",
            svix_timestamp=str(int(time.time())),
            svix_signature="v1,invalid_signature",
        )
