"""Integration tests for `SqlAlchemyUserRepository` against a real Postgres DB."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.exceptions import EmailAlreadyRegisteredError
from app.domain.user import User
from app.infrastructure.db.repositories import SqlAlchemyUserRepository
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = pytest.mark.integration


async def test_add_and_get_by_email(db_session: AsyncSession) -> None:
    repo = SqlAlchemyUserRepository(db_session)
    user = User.create(
        email="New@Example.com", hashed_password="hashed", now=datetime.now(UTC)
    )
    await repo.add(user)
    await db_session.commit()

    fetched = await repo.get_by_email("new@example.com")
    assert fetched is not None
    assert fetched.email == "new@example.com"
    assert fetched.id == user.id


async def test_duplicate_email_raises_conflict(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(UTC)
    first = User.create(email="dup@example.com", hashed_password="h1", now=now)
    second = User.create(email="dup@example.com", hashed_password="h2", now=now)

    uow = SqlAlchemyUnitOfWork(session_factory)
    async with uow:
        await uow.users.add(first)
        await uow.commit()

    async with uow:
        await uow.users.add(second)
        with pytest.raises(EmailAlreadyRegisteredError):
            await uow.commit()
