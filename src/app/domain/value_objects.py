"""Pure domain value-object rules (design ADR-02).

Every function here is a stateless, framework-free validator that either
returns a normalized value or raises a domain exception. Constants are
exported so API schemas can reuse the same limits in their field
definitions (design ADR-13), keeping the domain the single source of truth.
"""

from datetime import date
from enum import StrEnum

from app.domain.exceptions import (
    DueDateInPastError,
    InvalidFieldError,
    PasswordPolicyError,
)

NAME_MAX_LENGTH = 120
DESCRIPTION_MAX_LENGTH = 2000
TITLE_MAX_LENGTH = 200


class TaskStatus(StrEnum):
    """A task's lifecycle state (tasks spec: strict state machine)."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class Priority(StrEnum):
    """A task's priority (tasks spec: create/update field validation)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


#: Only these edges are valid (tasks spec: strict state machine, confirmed
#: by the user to reject same-status transitions with 409 as well).
_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset({TaskStatus.IN_PROGRESS}),
    TaskStatus.IN_PROGRESS: frozenset({TaskStatus.PENDING, TaskStatus.DONE}),
    TaskStatus.DONE: frozenset({TaskStatus.IN_PROGRESS}),
}


def can_transition(source: TaskStatus, destination: TaskStatus) -> bool:
    """Return whether `source -> destination` is one of the four valid edges."""
    return destination in _TRANSITIONS[source]


def normalize_required_text(value: str, *, field: str, max_len: int) -> str:
    """Strip `value`; raise `InvalidFieldError` if blank or too long."""
    stripped = value.strip()
    if not stripped:
        raise InvalidFieldError(field, f"{field} must not be blank")
    if len(stripped) > max_len:
        raise InvalidFieldError(
            field, f"{field} must be at most {max_len} characters long"
        )
    return stripped


def normalize_optional_text(
    value: str | None, *, field: str, max_len: int
) -> str | None:
    """Strip `value`; blank becomes `None`. Raise on too-long content."""
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if len(stripped) > max_len:
        raise InvalidFieldError(
            field, f"{field} must be at most {max_len} characters long"
        )
    return stripped


def validate_password_policy(raw: str) -> None:
    """Raise `PasswordPolicyError` unless `raw` meets the password policy.

    Policy: 8-128 characters, at least one letter, and at least one digit.
    """
    if not (8 <= len(raw) <= 128):
        raise PasswordPolicyError()
    if not any(character.isalpha() for character in raw):
        raise PasswordPolicyError()
    if not any(character.isdigit() for character in raw):
        raise PasswordPolicyError()


def ensure_due_date_not_past(due_date: date | None, today: date) -> None:
    """Raise `DueDateInPastError` if `due_date` is earlier than `today`.

    `today` is a parameter, never read from the system clock (tasks spec:
    due_date compared against the injected clock's UTC date). `None` is
    always accepted.
    """
    if due_date is not None and due_date < today:
        raise DueDateInPastError()
