"""Integration tests for `SqlAlchemyTaskRepository` against a real Postgres
DB (design ADR-07/ADR-08): CRUD, the `status`/`priority` CHECK constraints,
cascade delete from the parent `TaskList`, and the nullable `assignee_id`
FK's `ON DELETE SET NULL` behavior (shipped now per ADR-08 even though
assignment use cases land in Phase 8).
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.task import Task
from app.domain.task_list import TaskList
from app.domain.user import User
from app.domain.value_objects import Priority
from app.infrastructure.db.models import TaskListModel, TaskModel, UserModel
from app.infrastructure.db.repositories import (
    SqlAlchemyTaskListRepository,
    SqlAlchemyTaskRepository,
    SqlAlchemyUserRepository,
)
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def _create_owner_and_list(db_session: AsyncSession) -> tuple[User, TaskList]:
    owner = User.create(
        email=f"{uuid4()}@example.com", hashed_password="hashed", now=_NOW
    )
    await SqlAlchemyUserRepository(db_session).add(owner)
    await db_session.commit()
    task_list = TaskList.create(
        owner_id=owner.id, name="Groceries", description=None, now=_NOW
    )
    await SqlAlchemyTaskListRepository(db_session).add(task_list)
    await db_session.commit()
    return owner, task_list


async def test_add_get_update_and_delete(db_session: AsyncSession) -> None:
    _, task_list = await _create_owner_and_list(db_session)
    repo = SqlAlchemyTaskRepository(db_session)
    task = Task.create(
        list_id=task_list.id,
        title="Buy milk",
        description="2%",
        priority=Priority.LOW,
        due_date=None,
        today=_NOW.date(),
        now=_NOW,
    )
    await repo.add(task)
    await db_session.commit()

    fetched = await repo.get(task.id)
    assert fetched is not None
    assert fetched.title == "Buy milk"
    assert fetched.description == "2%"

    fetched.rename("Buy oat milk", datetime(2026, 1, 2, tzinfo=UTC))
    await repo.update(fetched)
    await db_session.commit()
    updated = await repo.get(task.id)
    assert updated is not None
    assert updated.title == "Buy oat milk"

    await repo.delete(task.id)
    await db_session.commit()
    assert await repo.get(task.id) is None


async def test_status_check_constraint_rejects_invalid_value(
    db_session: AsyncSession,
) -> None:
    """Bypasses the domain/ORM `TaskStatus` enum entirely with a raw
    `INSERT` to prove the DB-level CHECK constraint is the backstop
    (design ADR-08)."""
    _, task_list = await _create_owner_and_list(db_session)

    with pytest.raises(IntegrityError):
        await db_session.execute(
            sa.text(
                "INSERT INTO tasks "
                "(id, list_id, title, status, priority, created_at, updated_at) "
                "VALUES (:id, :list_id, :title, :status, :priority, "
                ":created_at, :updated_at)"
            ),
            {
                "id": uuid4(),
                "list_id": task_list.id,
                "title": "Buy milk",
                "status": "bogus",
                "priority": "low",
                "created_at": _NOW,
                "updated_at": _NOW,
            },
        )


async def test_priority_check_constraint_rejects_invalid_value(
    db_session: AsyncSession,
) -> None:
    """Bypasses the domain/ORM `Priority` enum entirely with a raw
    `INSERT` to prove the DB-level CHECK constraint is the backstop
    (design ADR-08)."""
    _, task_list = await _create_owner_and_list(db_session)

    with pytest.raises(IntegrityError):
        await db_session.execute(
            sa.text(
                "INSERT INTO tasks "
                "(id, list_id, title, status, priority, created_at, updated_at) "
                "VALUES (:id, :list_id, :title, :status, :priority, "
                ":created_at, :updated_at)"
            ),
            {
                "id": uuid4(),
                "list_id": task_list.id,
                "title": "Buy milk",
                "status": "pending",
                "priority": "urgent",
                "created_at": _NOW,
                "updated_at": _NOW,
            },
        )


async def test_deleting_list_cascades_to_its_tasks(db_session: AsyncSession) -> None:
    _, task_list = await _create_owner_and_list(db_session)
    repo = SqlAlchemyTaskRepository(db_session)
    task = Task.create(
        list_id=task_list.id,
        title="Buy milk",
        description=None,
        priority=Priority.LOW,
        due_date=None,
        today=_NOW.date(),
        now=_NOW,
    )
    await repo.add(task)
    await db_session.commit()

    list_model = await db_session.get(TaskListModel, task_list.id)
    assert list_model is not None
    await db_session.delete(list_model)
    await db_session.commit()

    remaining = await db_session.execute(
        sa.select(TaskModel).where(TaskModel.id == task.id)
    )
    assert remaining.scalar_one_or_none() is None


async def test_deleting_assignee_sets_assignee_id_to_null(
    db_session: AsyncSession,
) -> None:
    owner, task_list = await _create_owner_and_list(db_session)
    assignee = User.create(
        email=f"{uuid4()}@example.com", hashed_password="hashed", now=_NOW
    )
    await SqlAlchemyUserRepository(db_session).add(assignee)
    await db_session.commit()
    repo = SqlAlchemyTaskRepository(db_session)
    task = Task.create(
        list_id=task_list.id,
        title="Buy milk",
        description=None,
        priority=Priority.LOW,
        due_date=None,
        today=_NOW.date(),
        now=_NOW,
    )
    task.assign(assignee.id, _NOW)
    await repo.add(task)
    await db_session.commit()

    assignee_model = await db_session.get(UserModel, assignee.id)
    assert assignee_model is not None
    await db_session.delete(assignee_model)
    await db_session.commit()

    updated = await repo.get(task.id)
    assert updated is not None
    assert updated.assignee_id is None


async def test_unmapped_constraint_violation_is_re_raised_unmodified(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A constraint violation with no entry in `_CONSTRAINT_ERRORS` (here,
    `fk_tasks_list_id_task_lists` -- never a domain error) propagates as
    the raw `IntegrityError`, unmodified, confirming `SqlAlchemyUnitOfWork`
    only translates the constraint names it knows about and never
    swallows an unknown one (design ADR-07; Phase 6 REFACTOR task 6.7)."""
    uow = SqlAlchemyUnitOfWork(session_factory)
    task = Task.create(
        list_id=uuid4(),  # no such task_lists row exists
        title="Buy milk",
        description=None,
        priority=Priority.LOW,
        due_date=None,
        today=_NOW.date(),
        now=_NOW,
    )

    async with uow:
        await uow.tasks.add(task)
        with pytest.raises(IntegrityError):
            await uow.commit()
