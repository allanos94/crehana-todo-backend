"""Unit tests for the single application-layer authorization policy
(design ADR-06, task-lists spec: non-owner and nonexistent both -> 404,
never 403). Extended by later slices with `status_changeable_task`.
"""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from app.application.authorization import AccessPolicy
from app.domain.exceptions import TaskListNotFoundError, TaskNotFoundError
from app.domain.task import Task
from app.domain.task_list import TaskList
from app.domain.value_objects import Priority
from tests.unit.fakes import FakeUnitOfWork

_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_TODAY = date(2026, 1, 1)


async def test_owned_list_returns_list_for_owner() -> None:
    uow = FakeUnitOfWork()
    owner_id = uuid4()
    task_list = TaskList.create(
        owner_id=owner_id, name="Groceries", description=None, now=_NOW
    )
    await uow.task_lists.add(task_list)
    policy = AccessPolicy(uow)

    result = await policy.owned_list(task_list.id, owner_id)

    assert result.id == task_list.id


async def test_owned_list_raises_not_found_for_non_owner_and_missing() -> None:
    uow = FakeUnitOfWork()
    owner_id = uuid4()
    stranger_id = uuid4()
    task_list = TaskList.create(
        owner_id=owner_id, name="Groceries", description=None, now=_NOW
    )
    await uow.task_lists.add(task_list)
    policy = AccessPolicy(uow)

    with pytest.raises(TaskListNotFoundError):
        await policy.owned_list(task_list.id, stranger_id)

    with pytest.raises(TaskListNotFoundError):
        await policy.owned_list(uuid4(), owner_id)


async def test_owned_task_requires_list_ownership_then_task_membership() -> None:
    uow = FakeUnitOfWork()
    owner_id = uuid4()
    stranger_id = uuid4()
    task_list = TaskList.create(
        owner_id=owner_id, name="Groceries", description=None, now=_NOW
    )
    await uow.task_lists.add(task_list)
    other_list = TaskList.create(
        owner_id=owner_id, name="Work", description=None, now=_NOW
    )
    await uow.task_lists.add(other_list)
    task = Task.create(
        list_id=task_list.id,
        title="Buy milk",
        description=None,
        priority=Priority.LOW,
        due_date=None,
        today=_TODAY,
        now=_NOW,
    )
    await uow.tasks.add(task)
    other_list_task = Task.create(
        list_id=other_list.id,
        title="Unrelated",
        description=None,
        priority=Priority.LOW,
        due_date=None,
        today=_TODAY,
        now=_NOW,
    )
    await uow.tasks.add(other_list_task)
    policy = AccessPolicy(uow)

    result = await policy.owned_task(task_list.id, task.id, owner_id)
    assert result.id == task.id

    # Missing list -> 404.
    with pytest.raises(TaskListNotFoundError):
        await policy.owned_task(uuid4(), task.id, owner_id)

    # Non-owner -> 404 (via the list check).
    with pytest.raises(TaskListNotFoundError):
        await policy.owned_task(task_list.id, task.id, stranger_id)

    # Task belonging to a different list under the same owner -> 404.
    with pytest.raises(TaskNotFoundError):
        await policy.owned_task(task_list.id, other_list_task.id, owner_id)

    # Nonexistent task -> 404.
    with pytest.raises(TaskNotFoundError):
        await policy.owned_task(task_list.id, uuid4(), owner_id)
