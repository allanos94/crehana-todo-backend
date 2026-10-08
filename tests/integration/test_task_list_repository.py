"""Integration tests for `SqlAlchemyTaskListRepository` against a real
Postgres DB (design ADR-07/ADR-08/ADR-10): CRUD, the functional
case-insensitive unique index (`uq_task_lists_owner_id_lower_name`)
raising `IntegrityError` -> `DuplicateTaskListNameError` on a collision,
and the `owner_id` FK `ON DELETE CASCADE` behavior.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.exceptions import DuplicateTaskListNameError
from app.domain.task_list import TaskList
from app.domain.user import User
from app.infrastructure.db.models import TaskListModel, UserModel
from app.infrastructure.db.repositories import (
    SqlAlchemyTaskListRepository,
    SqlAlchemyUserRepository,
)
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def _create_owner(db_session: AsyncSession) -> User:
    owner = User.create(
        email=f"{uuid4()}@example.com", hashed_password="hashed", now=_NOW
    )
    await SqlAlchemyUserRepository(db_session).add(owner)
    await db_session.commit()
    return owner


async def test_add_get_update_and_delete(db_session: AsyncSession) -> None:
    owner = await _create_owner(db_session)
    repo = SqlAlchemyTaskListRepository(db_session)
    task_list = TaskList.create(
        owner_id=owner.id, name="Groceries", description="buy milk", now=_NOW
    )
    await repo.add(task_list)
    await db_session.commit()

    fetched = await repo.get(task_list.id)
    assert fetched is not None
    assert fetched.name == "Groceries"
    assert fetched.description == "buy milk"

    fetched.rename("Work", datetime(2026, 1, 2, tzinfo=UTC))
    await repo.update(fetched)
    await db_session.commit()
    updated = await repo.get(task_list.id)
    assert updated is not None
    assert updated.name == "Work"

    await repo.delete(task_list.id)
    await db_session.commit()
    assert await repo.get(task_list.id) is None


async def test_list_by_owner_returns_only_that_owners_lists(
    db_session: AsyncSession,
) -> None:
    owner = await _create_owner(db_session)
    other_owner = await _create_owner(db_session)
    repo = SqlAlchemyTaskListRepository(db_session)
    await repo.add(
        TaskList.create(owner_id=owner.id, name="Work", description=None, now=_NOW)
    )
    await repo.add(
        TaskList.create(
            owner_id=other_owner.id, name="Other", description=None, now=_NOW
        )
    )
    await db_session.commit()

    results = await repo.list_by_owner(owner.id)

    assert [task_list.name for task_list in results] == ["Work"]


async def test_name_exists_is_case_insensitive_and_excludes_id(
    db_session: AsyncSession,
) -> None:
    owner = await _create_owner(db_session)
    repo = SqlAlchemyTaskListRepository(db_session)
    task_list = TaskList.create(
        owner_id=owner.id, name="Groceries", description=None, now=_NOW
    )
    await repo.add(task_list)
    await db_session.commit()

    assert await repo.name_exists(owner.id, "GROCERIES") is True
    assert await repo.name_exists(owner.id, "groceries", exclude_id=task_list.id) is (
        False
    )
    assert await repo.name_exists(owner.id, "Nonexistent") is False


async def test_functional_unique_index_raises_on_case_insensitive_collision(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    owner = User.create(email="dup-list@example.com", hashed_password="h", now=_NOW)
    uow = SqlAlchemyUnitOfWork(session_factory)
    async with uow:
        await uow.users.add(owner)
        await uow.commit()

    first = TaskList.create(
        owner_id=owner.id, name="Groceries", description=None, now=_NOW
    )
    second = TaskList.create(
        owner_id=owner.id, name="GROCERIES", description=None, now=_NOW
    )

    async with uow:
        await uow.task_lists.add(first)
        await uow.commit()

    async with uow:
        await uow.task_lists.add(second)
        with pytest.raises(DuplicateTaskListNameError):
            await uow.commit()


async def test_deleting_owner_cascades_to_their_task_lists(
    db_session: AsyncSession,
) -> None:
    owner = await _create_owner(db_session)
    repo = SqlAlchemyTaskListRepository(db_session)
    task_list = TaskList.create(
        owner_id=owner.id, name="Groceries", description=None, now=_NOW
    )
    await repo.add(task_list)
    await db_session.commit()

    owner_model = await db_session.get(UserModel, owner.id)
    assert owner_model is not None
    await db_session.delete(owner_model)
    await db_session.commit()

    remaining = await db_session.execute(
        select(TaskListModel).where(TaskListModel.id == task_list.id)
    )
    assert remaining.scalar_one_or_none() is None
