import logging

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.core.logger import RequestLoggingMiddleware, _format_payload, _mask_sensitive_data


def test_mask_sensitive_data():
    sample = {
        "password": "supersecretpassword",
        "api_key": "re_1234567890",
        "token": "bearer xyz",
        "email": "user@example.com",
        "nested": {
            "secret": "my-secret",
            "normal": "value",
        },
        "items": [{"jwt": "abc", "count": 1}],
    }
    masked = _mask_sensitive_data(sample)
    assert masked["password"] == "***"
    assert masked["api_key"] == "***"
    assert masked["token"] == "***"
    assert masked["email"] == "user@example.com"
    assert masked["nested"]["secret"] == "***"
    assert masked["nested"]["normal"] == "value"
    assert masked["items"][0]["jwt"] == "***"
    assert masked["items"][0]["count"] == 1


def test_format_payload():
    assert _format_payload(b"") == "<empty>"
    formatted = _format_payload(b'{"user":"john","password":"secret"}')
    assert "john" in formatted
    assert "***" in formatted
    assert "secret" not in formatted


@pytest.mark.asyncio
async def test_middleware_logging(caplog):
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.post("/test-log")
    async def sample_endpoint(payload: dict):
        return {"status": "ok", "echo": payload}

    @app.get("/test-error")
    async def error_endpoint():
        raise HTTPException(status_code=400, detail="Test bad request")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with caplog.at_level(logging.INFO):
            res = await client.post("/test-log?param=1", json={"name": "Alice", "password": "pass"})
            assert res.status_code == 200
            assert res.json()["status"] == "ok"

            # Verify log output captured request, response, endpoint, and status
            records = [r.message for r in caplog.records]
            matching = [r for r in records if "HTTP POST /test-log?param=1" in r]
            assert len(matching) >= 1
            log_line = matching[0]
            assert "HTTP POST /test-log?param=1 -> 200" in log_line
            assert "Alice" in log_line
            assert "***" in log_line
            assert '"status":"ok"' in log_line

        with caplog.at_level(logging.WARNING):
            res_err = await client.get("/test-error")
            assert res_err.status_code == 400
            err_records = [r.message for r in caplog.records]
            matching_err = [r for r in err_records if "HTTP GET /test-error -> 400" in r]
            assert len(matching_err) >= 1
