"""Tests for pure domain value-object rules (design ADR-02)."""

from datetime import date

import pytest

from app.domain.exceptions import (
    DueDateInPastError,
    InvalidFieldError,
    PasswordPolicyError,
)
from app.domain.value_objects import (
    Priority,
    TaskStatus,
    can_transition,
    ensure_due_date_not_past,
    normalize_optional_text,
    normalize_required_text,
    validate_password_policy,
)


def test_normalize_required_text_strips_and_returns() -> None:
    assert (
        normalize_required_text("  Groceries  ", field="name", max_len=120)
        == "Groceries"
    )


def test_normalize_required_text_rejects_blank_after_strip() -> None:
    with pytest.raises(InvalidFieldError) as exc_info:
        normalize_required_text("   ", field="name", max_len=120)
    assert exc_info.value.field == "name"


def test_normalize_required_text_rejects_too_long() -> None:
    with pytest.raises(InvalidFieldError):
        normalize_required_text("x" * 121, field="name", max_len=120)


def test_normalize_optional_text_returns_none_for_none() -> None:
    assert normalize_optional_text(None, field="description", max_len=2000) is None


def test_normalize_optional_text_returns_none_for_blank() -> None:
    assert normalize_optional_text("   ", field="description", max_len=2000) is None


def test_normalize_optional_text_strips_and_returns() -> None:
    result = normalize_optional_text("  buy milk  ", field="description", max_len=2000)
    assert result == "buy milk"


def test_normalize_optional_text_rejects_too_long() -> None:
    with pytest.raises(InvalidFieldError):
        normalize_optional_text("x" * 2001, field="description", max_len=2000)


@pytest.mark.parametrize(
    ("password", "should_raise"),
    [
        ("short1", True),  # too short (< 8)
        ("x" * 129 + "1", True),  # too long (> 128)
        ("OnlyLetters", True),  # no digit
        ("12345678", True),  # no letter
        ("Passw0rd1", False),  # valid
    ],
)
def test_validate_password_policy(password: str, should_raise: bool) -> None:
    if should_raise:
        with pytest.raises(PasswordPolicyError):
            validate_password_policy(password)
    else:
        validate_password_policy(password)  # must not raise


@pytest.mark.parametrize(
    ("source", "destination", "expected"),
    [
        (TaskStatus.PENDING, TaskStatus.IN_PROGRESS, True),
        (TaskStatus.IN_PROGRESS, TaskStatus.PENDING, True),
        (TaskStatus.IN_PROGRESS, TaskStatus.DONE, True),
        (TaskStatus.DONE, TaskStatus.IN_PROGRESS, True),
        (TaskStatus.PENDING, TaskStatus.DONE, False),
        (TaskStatus.DONE, TaskStatus.PENDING, False),
        (TaskStatus.PENDING, TaskStatus.PENDING, False),
        (TaskStatus.IN_PROGRESS, TaskStatus.IN_PROGRESS, False),
        (TaskStatus.DONE, TaskStatus.DONE, False),
    ],
)
def test_can_transition(
    source: TaskStatus, destination: TaskStatus, expected: bool
) -> None:
    assert can_transition(source, destination) is expected


def test_priority_values() -> None:
    assert {priority.value for priority in Priority} == {"low", "medium", "high"}


def test_ensure_due_date_not_past_rejects_past_date() -> None:
    today = date(2026, 10, 7)
    with pytest.raises(DueDateInPastError):
        ensure_due_date_not_past(date(2026, 10, 6), today)


def test_ensure_due_date_not_past_accepts_today() -> None:
    today = date(2026, 10, 7)
    ensure_due_date_not_past(today, today)  # must not raise


def test_ensure_due_date_not_past_accepts_future_date() -> None:
    today = date(2026, 10, 7)
    ensure_due_date_not_past(date(2026, 10, 8), today)  # must not raise


def test_ensure_due_date_not_past_accepts_none() -> None:
    ensure_due_date_not_past(None, date(2026, 10, 7))  # must not raise
