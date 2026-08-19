from datetime import UTC, datetime


def utc_now() -> datetime:
    """Returns the current timezone-aware UTC datetime."""
    return datetime.now(UTC)


def utc_now_iso() -> str:
    """Returns the current UTC datetime as an ISO-8601 formatted string."""
    return utc_now().isoformat()
