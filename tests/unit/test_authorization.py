"""Unit tests for the single application-layer authorization policy
(design ADR-06, task-lists spec: non-owner and nonexistent both -> 404,
never 403). Extended by later slices with `owned_task` and
`status_changeable_task`.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.application.authorization import AccessPolicy
from app.domain.exceptions import TaskListNotFoundError
from app.domain.task_list import TaskList
from tests.unit.fakes import FakeUnitOfWork

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


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
