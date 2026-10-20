"""Interview campaign state machine — invalid transitions are rejected."""
from __future__ import annotations

from datetime import datetime, timezone

DRAFT, PREPARED, PENDING, APPROVED, SCHEDULED, ACTIVE, COMPLETED, CLOSED, CANCELLED = (
    "draft", "requirements_prepared", "pending_approval", "approved", "scheduled", "active", "completed", "closed", "cancelled")

TRANSITIONS: dict[str, set[str]] = {
    DRAFT: {PREPARED, PENDING, APPROVED, CANCELLED},
    PREPARED: {PENDING, APPROVED, DRAFT, CANCELLED},
    PENDING: {APPROVED, DRAFT, CANCELLED},
    APPROVED: {SCHEDULED, ACTIVE, PENDING, DRAFT, CANCELLED},
    SCHEDULED: {ACTIVE, APPROVED, CANCELLED},
    ACTIVE: {COMPLETED, CLOSED, CANCELLED},
    COMPLETED: {CLOSED},
    CLOSED: set(),
    CANCELLED: set(),
}

EDITABLE = {DRAFT, PREPARED, PENDING, APPROVED}


class TransitionError(ValueError):
    pass


def assert_transition(current: str, target: str) -> None:
    if target not in TRANSITIONS.get(current, set()):
        raise TransitionError(f"Cannot move interview from '{current}' to '{target}'")


def can_activate(*, status: str, skill_approval_state: str, has_approved_skills: bool) -> tuple[bool, str]:
    if status not in (APPROVED, SCHEDULED):
        return False, f"Interview must be approved before activation (current: {status})"
    if skill_approval_state not in ("approved", "not_required"):
        return False, "Required skills must be approved by the institution before activation"
    if not has_approved_skills:
        return False, "At least one approved required skill is needed"
    return True, "ok"


def within_schedule(start: datetime | None, end: datetime | None, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    if start and now < start:
        return False
    if end and now > end:
        return False
    return True


def activation_target(start: datetime | None, now: datetime | None = None) -> str:
    """Activating before the start time schedules the interview; it becomes joinable at start."""
    now = now or datetime.now(timezone.utc)
    return SCHEDULED if start and start > now else ACTIVE


def effective_status(status: str, start: datetime | None, end: datetime | None, now: datetime | None = None) -> str:
    """Scheduled interviews become active at start time; active interviews complete after end time."""
    now = now or datetime.now(timezone.utc)
    if status == SCHEDULED and start and now >= start and (not end or now <= end):
        return ACTIVE
    if status in (SCHEDULED, ACTIVE) and end and now > end:
        return COMPLETED
    return status
