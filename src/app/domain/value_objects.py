"""Pure domain value-object rules (design ADR-02).

Every function here is a stateless, framework-free validator that either
returns a normalized value or raises a domain exception. Constants are
exported so API schemas can reuse the same limits in their field
definitions (design ADR-13), keeping the domain the single source of truth.
"""

from app.domain.exceptions import InvalidFieldError, PasswordPolicyError

NAME_MAX_LENGTH = 120
DESCRIPTION_MAX_LENGTH = 2000


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
