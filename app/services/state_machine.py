"""
Payment State Machine

Enforces valid payment status transitions and logs every state change
to the payment_state_transitions audit table.

Valid transitions:
  CREATED → PENDING, EXPIRED, FAILED
  PENDING → PROCESSING, EXPIRED, FAILED
  PROCESSING → CONFIRMED, PAID, FAILED
  CONFIRMED → REFUNDED, PARTIALLY_REFUNDED
  PAID → REFUNDED, PARTIALLY_REFUNDED
  FAILED → CREATED  (retry)
  EXPIRED → CREATED  (retry)
"""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import (
    PaymentSession,
    PaymentStatus,
    PaymentEvent,
    PaymentStateTransition,
)

logger = logging.getLogger(__name__)

# Allowed transitions: from_state → set of allowed to_states
VALID_TRANSITIONS: dict[PaymentStatus, set[PaymentStatus]] = {
    PaymentStatus.CREATED: {
        PaymentStatus.PENDING,
        PaymentStatus.EXPIRED,
        PaymentStatus.FAILED,
    },
    PaymentStatus.PENDING: {
        PaymentStatus.PROCESSING,
        PaymentStatus.CONFIRMED,
        PaymentStatus.PAID,
        PaymentStatus.EXPIRED,
        PaymentStatus.FAILED,
    },
    PaymentStatus.PROCESSING: {
        PaymentStatus.CONFIRMED,
        PaymentStatus.PAID,
        PaymentStatus.FAILED,
    },
    PaymentStatus.CONFIRMED: {
        PaymentStatus.REFUNDED,
        PaymentStatus.PARTIALLY_REFUNDED,
    },
    PaymentStatus.PAID: {
        PaymentStatus.REFUNDED,
        PaymentStatus.PARTIALLY_REFUNDED,
    },
    PaymentStatus.FAILED: {
        PaymentStatus.CREATED,  # retry
    },
    PaymentStatus.EXPIRED: {
        PaymentStatus.CREATED,  # retry
    },
    PaymentStatus.REFUNDED: set(),
    PaymentStatus.PARTIALLY_REFUNDED: {
        PaymentStatus.REFUNDED,
    },
}


class InvalidTransitionError(Exception):
    """Raised when a payment state transition is not allowed."""

    def __init__(self, from_state: PaymentStatus, to_state: PaymentStatus):
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Invalid transition: {from_state.value} → {to_state.value}"
        )


def can_transition(from_state: PaymentStatus, to_state: PaymentStatus) -> bool:
    allowed = VALID_TRANSITIONS.get(from_state, set())
    return to_state in allowed


def transition_payment(
    session: PaymentSession,
    to_state: PaymentStatus,
    db: Session,
    *,
    trigger: Optional[str] = None,
    actor: str = "system",
    metadata: Optional[dict] = None,
) -> PaymentSession:
    """
    Transition a payment session to a new state.

    Validates the transition, updates the session, creates a
    PaymentStateTransition audit record and a PaymentEvent.

    Raises InvalidTransitionError if the transition is not allowed.
    """
    from_state = session.status

    if not can_transition(from_state, to_state):
        raise InvalidTransitionError(from_state, to_state)

    # Update session
    session.status = to_state
    if to_state in (PaymentStatus.CONFIRMED, PaymentStatus.PAID):
        session.paid_at = datetime.utcnow()

    # Audit: state transition
    transition = PaymentStateTransition(
        session_id=session.id,
        from_state=from_state.value,
        to_state=to_state.value,
        trigger=trigger,
        actor=actor,
        transition_metadata=metadata,
    )
    db.add(transition)

    # Audit: payment event
    event = PaymentEvent(
        session_id=session.id,
        event_type=f"status.{to_state.value}",
        chain=session.chain,
        tx_hash=session.tx_hash,
        details={
            "from": from_state.value,
            "to": to_state.value,
            "trigger": trigger,
            "actor": actor,
        },
    )
    db.add(event)

    db.flush()

    logger.info(
        "Payment %s: %s → %s (trigger=%s, actor=%s)",
        session.id,
        from_state.value,
        to_state.value,
        trigger,
        actor,
    )

    return session
