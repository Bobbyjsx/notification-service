import base64
import hashlib
import hmac
import time
from typing import Any

import jwt
from jwt import PyJWKClient, PyJWTError
from pydantic import BaseModel

from app.core.config import settings
from app.core.errors import AuthenticationError, WebhookVerificationError


class ServiceIdentity(BaseModel):
    """Represents an authenticated platform service."""

    sub: str
    app_id: str
    token_type: str = "service"
    scopes: list[str] = []
    metadata: dict[str, Any] = {}


_jwks_client: PyJWKClient | None = None


def get_jwks_client() -> PyJWKClient | None:
    """Returns or initializes the PyJWKClient for fetching Identity Service public keys."""
    global _jwks_client
    if _jwks_client is None and settings.identity_jwks_url:
        _jwks_client = PyJWKClient(
            settings.identity_jwks_url,
            cache_jwk_set=True,
            lifespan=3600,
            headers={"User-Agent": f"Mozilla/5.0 (compatible; {settings.service_name})"},
        )
    return _jwks_client


def verify_service_token(token: str) -> ServiceIdentity:
    """
    Verifies a service JWT issued by the Identity Service.
    Enforces issuer, audience, and token type.
    """
    if not token:
        raise AuthenticationError("Missing service token")

    errors: list[str] = []

    # 1. Attempt JWKS / Identity Service EdDSA public key verification
    jwk_client = get_jwks_client()
    if jwk_client:
        try:
            signing_key = jwk_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["EdDSA", "RS256", "ES256"],
                issuer=settings.identity_issuer,
                audience=settings.identity_audience,
                options={"verify_aud": True, "verify_iss": True},
            )
        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Service token has expired")
        except jwt.InvalidIssuerError as exc:
            raise AuthenticationError(f"Service token issuer mismatch: {exc}")
        except jwt.InvalidAudienceError as exc:
            raise AuthenticationError(f"Service token audience mismatch: {exc}")
        except Exception as exc:
            errors.append(f"JWKS verification failed: {exc}")
            payload = None

    # 2. Development / testing fallback with symmetric secret key if configured
    if payload is None and settings.jwt_secret_key:
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm, "HS256"],
                issuer=settings.identity_issuer,
                audience=settings.identity_audience,
                options={"verify_aud": True, "verify_iss": True},
            )
        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Service token has expired")
        except jwt.InvalidIssuerError as exc:
            raise AuthenticationError(f"Service token issuer mismatch: {exc}")
        except jwt.InvalidAudienceError as exc:
            raise AuthenticationError(f"Service token audience mismatch: {exc}")
        except Exception as exc:
            errors.append(f"Secret key verification failed: {exc}")
            payload = None

    if payload is None:
        err_detail = "; ".join(errors) if errors else "No valid JWKS or secret configured"
        raise AuthenticationError(f"Could not validate service token credentials ({err_detail})")

    token_type = payload.get("type", "service")
    if token_type == "refresh":
        raise AuthenticationError("Refresh tokens cannot be used as service tokens")

    sub = payload.get("sub", "")
    app_id = payload.get("app_id", sub.replace("service:", ""))

    if not sub or not app_id:
        raise AuthenticationError("Service token payload missing required identity claims")

    return ServiceIdentity(
        sub=sub,
        app_id=app_id,
        token_type=token_type,
        scopes=payload.get("scopes", []),
        metadata={"jti": payload.get("jti"), "iat": payload.get("iat")},
    )


def verify_resend_webhook_signature(
    payload_body: bytes,
    svix_id: str | None,
    svix_timestamp: str | None,
    svix_signature: str | None,
    tolerance_seconds: int = 300,
) -> bool:
    """
    Verifies standard Svix/Resend webhook signatures using HMAC-SHA256.
    """
    if not settings.resend_webhook_secret:
        if settings.environment == "development" or settings.enable_mock_delivery:
            return True
        raise WebhookVerificationError("Webhook secret is not configured on server")

    if not svix_id or not svix_timestamp or not svix_signature:
        raise WebhookVerificationError("Missing required Svix webhook headers")

    # Verify timestamp freshness to prevent replay attacks
    try:
        ts = int(svix_timestamp)
        now = int(time.time())
        if abs(now - ts) > tolerance_seconds:
            raise WebhookVerificationError("Webhook timestamp is outside tolerance window")
    except ValueError:
        raise WebhookVerificationError("Invalid webhook timestamp format")

    # Format secret: strip 'whsec_' prefix if present and decode base64
    raw_secret = settings.resend_webhook_secret.removeprefix("whsec_")
    try:
        secret_bytes = base64.b64decode(raw_secret)
    except Exception:
        secret_bytes = raw_secret.encode("utf-8")

    # Canonical message to sign: "{svix_id}.{svix_timestamp}.{payload_body}"
    to_sign = f"{svix_id}.{svix_timestamp}.".encode() + payload_body
    computed_sig = hmac.new(secret_bytes, to_sign, hashlib.sha256).digest()
    expected_b64 = base64.b64encode(computed_sig).decode("utf-8")

    # svix-signature header format: "v1,signature_b64 v1,other_b64..."
    signatures = svix_signature.split(" ")
    verified = False
    for item in signatures:
        parts = item.split(",", 1)
        if len(parts) == 2 and parts[0] == "v1":
            sig_to_check = parts[1]
            if hmac.compare_digest(expected_b64, sig_to_check):
                verified = True
                break

    if not verified:
        raise WebhookVerificationError("Resend webhook signature verification failed")

    return True
