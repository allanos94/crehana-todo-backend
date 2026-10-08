"""Tests for pure domain value-object rules (design ADR-02)."""

import pytest

from app.domain.exceptions import InvalidFieldError, PasswordPolicyError
from app.domain.value_objects import (
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
