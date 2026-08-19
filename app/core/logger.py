import logging
import sys
import time
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("notification_service")


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
    """Middleware for non-sensitive HTTP request/response metrics and logging."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.perf_counter()
        method = request.method
        path = request.url.path

        # Ignore noisy health check requests in normal logging
        is_health = path in {"/health", "/healthz"}

        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000

            if not is_health:
                status_code = response.status_code
                if status_code >= 500:
                    logger.error(
                        "HTTP %s %s -> %d (%.2fms)",
                        method,
                        path,
                        status_code,
                        duration_ms,
                    )
                elif status_code >= 400:
                    logger.warning(
                        "HTTP %s %s -> %d (%.2fms)",
                        method,
                        path,
                        status_code,
                        duration_ms,
                    )
                else:
                    logger.info(
                        "HTTP %s %s -> %d (%.2fms)",
                        method,
                        path,
                        status_code,
                        duration_ms,
                    )
            return response
        except Exception:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.exception("HTTP %s %s failed with unhandled exception (%.2fms)", method, path, duration_ms)
            raise
