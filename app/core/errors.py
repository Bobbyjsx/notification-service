from typing import Any


class NotificationError(Exception):
    """Base domain exception for the Notification Service."""

    def __init__(
        self,
        message: str,
        code: str = "NOTIFICATION_ERROR",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class AuthenticationError(NotificationError):
    """Raised when request authentication fails."""

    def __init__(self, message: str = "Authentication failed", details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            code="AUTHENTICATION_FAILED",
            status_code=401,
            details=details,
        )


class AuthorizationError(NotificationError):
    """Raised when an authenticated service is not permitted to perform an action."""

    def __init__(self, message: str = "Permission denied", details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            code="FORBIDDEN",
            status_code=403,
            details=details,
        )


class NotFoundError(NotificationError):
    """Raised when a requested resource does not exist."""

    def __init__(self, message: str = "Resource not found", details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            code="NOT_FOUND",
            status_code=404,
            details=details,
        )


class InvalidStateTransitionError(NotificationError):
    """Raised when an illegal notification status transition is attempted."""

    def __init__(
        self,
        current_status: str,
        target_status: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        message = f"Cannot transition notification from '{current_status}' to '{target_status}'"
        super().__init__(
            message=message,
            code="INVALID_STATE_TRANSITION",
            status_code=409,
            details=details or {"current_status": current_status, "target_status": target_status},
        )


class IdempotencyConflictError(NotificationError):
    """Raised when an idempotent operation conflicts with an ongoing or completed execution."""

    def __init__(self, message: str = "Idempotency conflict detected", details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            code="IDEMPOTENCY_CONFLICT",
            status_code=409,
            details=details,
        )


class TemplateRenderError(NotificationError):
    """Raised when template rendering or validation fails."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            code="TEMPLATE_RENDER_ERROR",
            status_code=400,
            details=details,
        )


class EventParsingError(NotificationError):
    """Raised when a platform event envelope or Pub/Sub payload is malformed."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            code="EVENT_PARSING_ERROR",
            status_code=400,
            details=details,
        )


class WebhookVerificationError(NotificationError):
    """Raised when an incoming provider webhook fails signature verification."""

    def __init__(self, message: str = "Invalid webhook signature", details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            code="INVALID_WEBHOOK_SIGNATURE",
            status_code=401,
            details=details,
        )


class ProviderError(NotificationError):
    """Base exception for third-party email provider failures."""

    def __init__(
        self,
        message: str,
        code: str = "PROVIDER_ERROR",
        status_code: int = 502,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=status_code,
            details=details,
        )


class TransientProviderError(ProviderError):
    """Transient provider error (e.g. rate limit, 5xx, timeout) that SHOULD be retried."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            code="PROVIDER_TRANSIENT_FAILURE",
            status_code=503,
            details=details,
        )


class PermanentProviderError(ProviderError):
    """Permanent provider error (e.g. invalid recipient, hard bounce) that should NOT be retried."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            code="PROVIDER_PERMANENT_FAILURE",
            status_code=422,
            details=details,
        )
