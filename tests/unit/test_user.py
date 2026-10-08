"""Tests for the `User` domain entity (design ADR-02, file-changes slice 1a)."""

from datetime import UTC, datetime
from uuid import UUID

from app.domain.user import User


def test_user_create_normalizes_email() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    user = User.create(email="  New@Example.com  ", hashed_password="hashed", now=now)
    assert user.email == "new@example.com"


def test_user_create_sets_identity_and_timestamp() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    user = User.create(email="user@example.com", hashed_password="hashed", now=now)
    assert isinstance(user.id, UUID)
    assert user.created_at == now
    assert user.hashed_password == "hashed"


def test_user_create_generates_unique_ids() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    first = User.create(email="a@example.com", hashed_password="h", now=now)
    second = User.create(email="b@example.com", hashed_password="h", now=now)
    assert first.id != second.id
