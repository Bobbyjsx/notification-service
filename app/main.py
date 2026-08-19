from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.config import settings
from app.core.database import get_db_client
from app.core.errors import NotificationError
from app.core.logger import RequestLoggingMiddleware, logger, setup_logging
from app.integrations.cloud_tasks import CloudTasksDispatcher
from app.integrations.mock import MockEmailProvider
from app.integrations.resend import ResendEmailProvider
from app.routers import (
    events_router,
    health_router,
    notifications_router,
    tasks_router,
    webhooks_router,
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds standard security headers to all responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for application startup and graceful shutdown."""
    setup_logging()
    logger.info("Initializing Notification Service on environment: %s", settings.environment)

    # 1. Initialize Firestore client
    db_client = get_db_client()
    app.state.db_client = db_client

    # 2. Initialize shared HTTP client for external integrations
    http_client = httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0))
    app.state.http_client = http_client

    # 3. Initialize Provider and Dispatcher
    if settings.enable_mock_delivery or not settings.resend_api_key:
        logger.info("Using MockEmailProvider for email delivery")
        app.state.email_provider = MockEmailProvider()
    else:
        logger.info("Using ResendEmailProvider for email delivery")
        app.state.email_provider = ResendEmailProvider(
            http_client=http_client,
            api_key=settings.resend_api_key,
            default_from=settings.default_from_email,
            base_url=settings.resend_api_base_url,
        )

    app.state.tasks_dispatcher = CloudTasksDispatcher(
        project=settings.cloud_tasks_project,
        location=settings.cloud_tasks_location,
        queue=settings.cloud_tasks_queue,
        worker_url=settings.cloud_tasks_worker_url,
        service_account_email=settings.cloud_tasks_service_account_email,
    )

    yield

    # Shutdown: clean up clients
    logger.info("Shutting down Notification Service...")
    await http_client.aclose()
    db_client.close()


app = FastAPI(
    title="Notification Service",
    description="Platform-level notification delivery service supporting asynchronous email dispatch and Resend tracking.",
    version="1.0.0",
    lifespan=lifespan,
)

# 1. Security Headers Middleware
app.add_middleware(SecurityHeadersMiddleware)

# 2. Request Logging Middleware
app.add_middleware(RequestLoggingMiddleware)

# 3. CORS Middleware with explicit origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# Exception Handlers
@app.exception_handler(NotificationError)
async def handle_domain_error(request: Request, exc: NotificationError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.code,
            "message": exc.message,
            "details": exc.details,
        },
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    formatted_errors = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", []))
        formatted_errors.append({
            "field": loc,
            "message": err.get("msg", "Invalid value"),
            "type": err.get("type", "value_error"),
        })

    first_msg = (
        f"Validation failed on '{formatted_errors[0]['field']}': {formatted_errors[0]['message']}"
        if formatted_errors
        else "Request validation failed"
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "VALIDATION_ERROR",
            "message": first_msg,
            "details": {"errors": formatted_errors},
        },
    )


@app.exception_handler(HTTPException)
async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    error_code = "HTTP_ERROR"
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        error_code = "AUTHENTICATION_FAILED"
    elif exc.status_code == status.HTTP_403_FORBIDDEN:
        error_code = "FORBIDDEN"
    elif exc.status_code == status.HTTP_404_NOT_FOUND:
        error_code = "NOT_FOUND"

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": error_code,
            "message": str(exc.detail),
            "details": {},
        },
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def handle_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled internal error: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "INTERNAL_SERVER_ERROR",
            "message": str(exc) if settings.environment == "development" else "Internal Server Error",
            "details": {"exception": str(exc)} if settings.environment == "development" else {},
        },
    )


# Unprefixed discovery/health routes
app.include_router(health_router)

# Versioned API routes
app.include_router(notifications_router, prefix=settings.api_v1_str)
app.include_router(events_router, prefix=settings.api_v1_str)
app.include_router(tasks_router, prefix=settings.api_v1_str)
app.include_router(webhooks_router, prefix=settings.api_v1_str)
