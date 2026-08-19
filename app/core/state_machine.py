from enum import StrEnum

from app.core.errors import InvalidStateTransitionError


class NotificationStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    BOUNCED = "bounced"
    COMPLAINED = "complained"


# Explicit valid state transition matrix
VALID_TRANSITIONS: dict[NotificationStatus, frozenset[NotificationStatus]] = {
    NotificationStatus.QUEUED: frozenset(
        {
            NotificationStatus.PROCESSING,
            NotificationStatus.FAILED,
        }
    ),
    NotificationStatus.PROCESSING: frozenset(
        {
            NotificationStatus.SENT,
            NotificationStatus.FAILED,
            NotificationStatus.QUEUED,  # On retry backoff
        }
    ),
    NotificationStatus.SENT: frozenset(
        {
            NotificationStatus.DELIVERED,
            NotificationStatus.BOUNCED,
            NotificationStatus.COMPLAINED,
            NotificationStatus.FAILED,
        }
    ),
    NotificationStatus.DELIVERED: frozenset(
        {
            NotificationStatus.BOUNCED,
            NotificationStatus.COMPLAINED,
        }
    ),
    NotificationStatus.FAILED: frozenset(
        {
            NotificationStatus.QUEUED,  # Allowed for manual re-try
        }
    ),
    NotificationStatus.BOUNCED: frozenset(),
    NotificationStatus.COMPLAINED: frozenset(),
}


def can_transition(current: str | NotificationStatus, target: str | NotificationStatus) -> bool:
    """Checks if a transition between two notification statuses is permitted."""
    current_status = NotificationStatus(current)
    target_status = NotificationStatus(target)

    # Identical state transition is a no-op / idempotent
    if current_status == target_status:
        return True

    allowed = VALID_TRANSITIONS.get(current_status, frozenset())
    return target_status in allowed


def assert_valid_transition(current: str | NotificationStatus, target: str | NotificationStatus) -> None:
    """Asserts that a state transition is valid, raising InvalidStateTransitionError otherwise."""
    current_status = NotificationStatus(current)
    target_status = NotificationStatus(target)

    if not can_transition(current_status, target_status):
        raise InvalidStateTransitionError(
            current_status=current_status.value,
            target_status=target_status.value,
        )
