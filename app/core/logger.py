import json
import logging
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("notification_service")

SENSITIVE_KEYS = {
    "password",
    "secret",
    "api_key",
    "apikey",
    "token",
    "jwt",
    "authorization",
    "access_token",
    "refresh_token",
    "secret_key",
}


def _mask_sensitive_data(data: Any) -> Any:
    """Recursively masks sensitive values in dictionaries and lists."""
    if isinstance(data, dict):
        masked = {}
        for k, v in data.items():
            if str(k).lower() in SENSITIVE_KEYS:
                masked[k] = "***"
            else:
                masked[k] = _mask_sensitive_data(v)
        return masked
    elif isinstance(data, list):
        return [_mask_sensitive_data(item) for item in data]
    return data


def _format_payload(raw_bytes: bytes, max_len: int = 4000) -> str:
    """Decodes and safely formats body payload for logging."""
    if not raw_bytes:
        return "<empty>"
    try:
        parsed = json.loads(raw_bytes.decode("utf-8"))
        masked = _mask_sensitive_data(parsed)
        formatted = json.dumps(masked, separators=(",", ":"))
    except Exception:
        text = raw_bytes.decode("utf-8", errors="replace")
        formatted = text

    if len(formatted) > max_len:
        return f"{formatted[:max_len]}... [truncated ({len(raw_bytes)} bytes)]"
    return formatted


def setup_logging(log_level: str = "INFO") -> None:
    """Configures root and application loggers with structured console output."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    # Clear existing handlers to avoid duplicates
    root_logger.handlers.clear()
    root_logger.addHandler(handler)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for structured HTTP request and response auditing with payload inspection."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.perf_counter()
        req_timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        method = request.method
        path = request.url.path
        query = request.url.query
        full_path = f"{path}?{query}" if query else path

        # Ignore noisy health check requests in normal logging unless they error
        is_health = path in {"/health", "/healthz"}

        # 1. Read request body safely
        try:
            req_body_bytes = await request.body()
        except Exception:
            req_body_bytes = b""

        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000

            # 2. Read response body from iterator
            res_body_chunks = [chunk async for chunk in response.body_iterator]

            async def _iterate_body():
                for chunk in res_body_chunks:
                    yield chunk

            response.body_iterator = _iterate_body()
            res_body_bytes = b"".join(res_body_chunks)

            if not is_health:
                status_code = response.status_code
                req_formatted = _format_payload(req_body_bytes)
                res_formatted = _format_payload(res_body_bytes)

                log_entry = (
                    f"[{req_timestamp}] HTTP {method} {full_path} -> {status_code} ({duration_ms:.2f}ms) "
                    f"| Request: {req_formatted} | Response: {res_formatted}"
                )

                if status_code >= 500:
                    logger.error(log_entry)
                elif status_code >= 400:
                    logger.warning(log_entry)
                else:
                    logger.info(log_entry)
            return response
        except Exception:
            duration_ms = (time.perf_counter() - start_time) * 1000
            req_formatted = _format_payload(req_body_bytes)
            logger.exception(
                "[%s] HTTP %s %s failed with unhandled exception (%.2fms) | Request: %s",
                req_timestamp,
                method,
                full_path,
                duration_ms,
                req_formatted,
            )
            raise
