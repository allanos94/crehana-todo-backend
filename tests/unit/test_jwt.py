"""Unit tests for `JwtTokenService` (user-auth spec: access/refresh expiry,
type enforcement in both directions, expired-token rejection, tampered
signature rejection).
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from app.application.exceptions import InvalidTokenError
from app.application.ports import TokenType
from app.infrastructure.security.jwt import JwtTokenService
from tests.unit.fakes import FixedClock

_SECRET = "test-only-secret-key-at-least-32-characters-long"
#: PyJWT validates `iat` against the real wall clock regardless of the
#: injected `Clock`, so "valid, unexpired" tokens must be issued at the real
#: current time, not an arbitrary fixed date (an `iat` in the future raises
#: `ImmatureSignatureError`). Only the expired-token test needs a fixed past
#: `issued_at`, since its token must already be past its `exp`.
#: PyJWT encodes `iat`/`exp` as integer Unix timestamps, truncating
#: microseconds, so `_NOW` is pre-truncated for an exact equality check.
_NOW = datetime.now(UTC).replace(microsecond=0)
_PAST = datetime(2000, 1, 1, tzinfo=UTC)


def _service(issued_at: datetime) -> JwtTokenService:
    return JwtTokenService(_SECRET, FixedClock(issued_at))


def test_access_token_expires_in_fifteen_minutes() -> None:
    pair = _service(_NOW).issue_pair(uuid4())

    payload = jwt.decode(pair.access_token, _SECRET, algorithms=["HS256"])
    exp = datetime.fromtimestamp(payload["exp"], tz=UTC)

    assert exp == _NOW + timedelta(minutes=15)


def test_refresh_token_expires_in_seven_days() -> None:
    pair = _service(_NOW).issue_pair(uuid4())

    payload = jwt.decode(pair.refresh_token, _SECRET, algorithms=["HS256"])
    exp = datetime.fromtimestamp(payload["exp"], tz=UTC)

    assert exp == _NOW + timedelta(days=7)


def test_decode_round_trips_the_user_id_for_each_type() -> None:
    user_id = uuid4()
    service = _service(_NOW)
    pair = service.issue_pair(user_id)

    assert service.decode(pair.access_token, TokenType.ACCESS) == user_id
    assert service.decode(pair.refresh_token, TokenType.REFRESH) == user_id


def test_refresh_token_rejected_as_access_token() -> None:
    service = _service(_NOW)
    pair = service.issue_pair(uuid4())

    with pytest.raises(InvalidTokenError):
        service.decode(pair.refresh_token, TokenType.ACCESS)


def test_access_token_rejected_as_refresh_token() -> None:
    service = _service(_NOW)
    pair = service.issue_pair(uuid4())

    with pytest.raises(InvalidTokenError):
        service.decode(pair.access_token, TokenType.REFRESH)


def test_expired_token_is_rejected() -> None:
    service = _service(_PAST)
    pair = service.issue_pair(uuid4())

    with pytest.raises(InvalidTokenError):
        service.decode(pair.access_token, TokenType.ACCESS)


def test_tampered_signature_is_rejected() -> None:
    service = _service(_NOW)
    pair = service.issue_pair(uuid4())
    last_char = pair.access_token[-1]
    tampered = pair.access_token[:-1] + ("A" if last_char != "A" else "B")

    with pytest.raises(InvalidTokenError):
        service.decode(tampered, TokenType.ACCESS)
