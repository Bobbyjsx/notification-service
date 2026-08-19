import httpx
import pytest

from app.core.errors import PermanentProviderError, TransientProviderError
from app.integrations.resend import ResendEmailProvider


@pytest.mark.asyncio
async def test_resend_success():
    def mock_handler(request: httpx.Request):
        assert request.headers["Authorization"] == "Bearer re_test_key"
        return httpx.Response(200, json={"id": "msg_resend_12345"})

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        provider = ResendEmailProvider(
            http_client=client,
            api_key="re_test_key",
            default_from="noreply@example.com",
        )
        result = await provider.send_email(
            to="user@example.com",
            subject="Test Subject",
            html_body="<p>Test</p>",
        )
        assert result.provider == "resend"
        assert result.message_id == "msg_resend_12345"


@pytest.mark.asyncio
async def test_resend_transient_error_429():
    def mock_handler(request: httpx.Request):
        return httpx.Response(429, json={"message": "Too many requests"})

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        provider = ResendEmailProvider(
            http_client=client,
            api_key="re_test_key",
        )
        with pytest.raises(TransientProviderError) as exc_info:
            await provider.send_email(
                to="user@example.com",
                subject="Test",
                html_body="<p>Test</p>",
            )
        assert "rate limit" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_resend_permanent_error_422():
    def mock_handler(request: httpx.Request):
        return httpx.Response(422, json={"message": "Invalid recipient email address"})

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        provider = ResendEmailProvider(
            http_client=client,
            api_key="re_test_key",
        )
        with pytest.raises(PermanentProviderError) as exc_info:
            await provider.send_email(
                to="invalid-email",
                subject="Test",
                html_body="<p>Test</p>",
            )
        assert "rejected request" in str(exc_info.value).lower()
