"""Tests for the `FakeUnitOfWork` rollback/commit semantics themselves.

Later use-case tests rely on these semantics (e.g. "no notification when
commit fails"), so they are worth testing directly rather than only
transitively.
"""

from datetime import UTC, datetime

from app.domain.user import User
from tests.unit.fakes import FakeUnitOfWork


async def test_commit_persists_changes() -> None:
    uow = FakeUnitOfWork()
    user = User.create(
        email="a@example.com", hashed_password="h", now=datetime.now(UTC)
    )

    async with uow:
        await uow.users.add(user)
        await uow.commit()

    assert uow.committed is True
    assert await uow.users.get_by_id(user.id) == user


async def test_rollback_restores_pre_transaction_snapshot() -> None:
    uow = FakeUnitOfWork()
    user = User.create(
        email="a@example.com", hashed_password="h", now=datetime.now(UTC)
    )

    async with uow:
        await uow.users.add(user)
        # No commit() call: __aexit__ must roll back.

    assert uow.committed is False
    assert await uow.users.get_by_id(user.id) is None
