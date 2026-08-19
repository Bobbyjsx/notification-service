import pytest

from app.core.errors import InvalidStateTransitionError
from app.core.state_machine import (
    NotificationStatus,
    assert_valid_transition,
    can_transition,
)


def test_valid_state_transitions():
    # Queued -> Processing
    assert can_transition(NotificationStatus.QUEUED, NotificationStatus.PROCESSING) is True
    # Processing -> Sent
    assert can_transition(NotificationStatus.PROCESSING, NotificationStatus.SENT) is True
    # Sent -> Delivered
    assert can_transition(NotificationStatus.SENT, NotificationStatus.DELIVERED) is True
    # Sent -> Bounced
    assert can_transition(NotificationStatus.SENT, NotificationStatus.BOUNCED) is True
    # Sent -> Complained
    assert can_transition(NotificationStatus.SENT, NotificationStatus.COMPLAINED) is True
    # Delivered -> Bounced
    assert can_transition(NotificationStatus.DELIVERED, NotificationStatus.BOUNCED) is True
    # Processing -> Failed
    assert can_transition(NotificationStatus.PROCESSING, NotificationStatus.FAILED) is True
    # Processing -> Queued (Retry)
    assert can_transition(NotificationStatus.PROCESSING, NotificationStatus.QUEUED) is True
    # Same status is idempotent
    assert can_transition(NotificationStatus.SENT, NotificationStatus.SENT) is True


def test_invalid_state_transitions():
    # Sent cannot transition back to Queued
    assert can_transition(NotificationStatus.SENT, NotificationStatus.QUEUED) is False
    # Delivered cannot transition back to Processing
    assert can_transition(NotificationStatus.DELIVERED, NotificationStatus.PROCESSING) is False
    # Bounced cannot transition to Sent
    assert can_transition(NotificationStatus.BOUNCED, NotificationStatus.SENT) is False
    # Complained cannot transition to Delivered
    assert can_transition(NotificationStatus.COMPLAINED, NotificationStatus.DELIVERED) is False


def test_assert_valid_transition_raises():
    with pytest.raises(InvalidStateTransitionError) as exc_info:
        assert_valid_transition(NotificationStatus.DELIVERED, NotificationStatus.QUEUED)
    assert "Cannot transition notification from 'delivered' to 'queued'" in str(exc_info.value)
