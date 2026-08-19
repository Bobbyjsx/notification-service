import logging
from typing import Any

import httpx

from app.core.config import settings
from app.core.errors import PermanentProviderError, ProviderError, TransientProviderError
from app.integrations.base import EmailProvider, EmailSendResult

logger = logging.getLogger(__name__)


class ResendEmailProvider(EmailProvider):
    """Resend email provider implementation using asynchronous HTTP client."""

    def __init__(
        self,
        http_client: httpx.AsyncClient | None = None,
        api_key: str | None = None,
        default_from: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.api_key = api_key or settings.resend_api_key
        self.default_from = default_from or settings.default_from_email
        self.base_url = (base_url or settings.resend_api_base_url).rstrip("/")
        self._external_client = http_client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._external_client:
            return self._external_client
        return httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0))

    async def send_email(
        self,
        *,
        to: str,
        subject: str,
        html_body: str,
        text_body: str | None = None,
        from_email: str | None = None,
        reply_to: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> EmailSendResult:
        if not self.api_key:
            raise PermanentProviderError("Resend API key is not configured")

        sender = from_email or self.default_from
        payload: dict[str, Any] = {
            "from": sender,
            "to": [to],
            "subject": subject,
            "html": html_body,
        }
        if text_body:
            payload["text"] = text_body
        if reply_to:
            payload["reply_to"] = reply_to
        if headers:
            payload["headers"] = headers

        request_headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "notification-service/1.0",
        }

        url = f"{self.base_url}/emails"
        client = await self._get_client()

        try:
            response = await client.post(url, json=payload, headers=request_headers)
        except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError, httpx.NetworkError) as exc:
            logger.warning("Resend network/timeout failure for recipient %s: %s", to, str(exc))
            raise TransientProviderError(f"Network error communicating with Resend: {exc}") from exc
        except Exception as exc:
            logger.exception("Unexpected error communicating with Resend: %s", str(exc))
            raise TransientProviderError(f"Unexpected provider error: {exc}") from exc
        finally:
            if not self._external_client:
                await client.aclose()

        status = response.status_code

        # Success case
        if 200 <= status < 300:
            try:
                res_data = response.json()
            except Exception:
                res_data = {}
            message_id = res_data.get("id", "")
            logger.info("Resend successfully accepted email for %s (id: %s)", to, message_id)
            return EmailSendResult(
                provider="resend",
                message_id=message_id,
                recipient=to,
                raw_response=res_data,
            )

        # Handle errors
        try:
            error_body = response.json()
            error_msg = error_body.get("message", response.text)
        except Exception:
            error_msg = response.text

        logger.error("Resend delivery failed with status %d: %s", status, error_msg)

        if status == 429:
            raise TransientProviderError(f"Resend rate limit exceeded (429): {error_msg}")
        elif status >= 500:
            raise TransientProviderError(f"Resend server error ({status}): {error_msg}")
        elif status in {400, 401, 403, 422}:
            raise PermanentProviderError(f"Resend rejected request ({status}): {error_msg}")
        else:
            raise ProviderError(f"Resend returned unexpected status ({status}): {error_msg}")
