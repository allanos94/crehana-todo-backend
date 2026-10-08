"""Unit tests for the task use cases against in-memory fakes (tasks spec:
CRUD, field validation, the due_date rule, the strict status state
machine -- owner path only; the assignee path is Phase 8).
"""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from app.application.tasks.dto import (
    ChangeTaskStatusCommand,
    CreateTaskCommand,
    DeleteTaskCommand,
    GetTaskCommand,
    UpdateTaskCommand,
)
from app.application.tasks.use_cases import (
    ChangeTaskStatus,
    CreateTask,
    DeleteTask,
    GetTask,
    UpdateTask,
)
from app.domain.exceptions import (
    DueDateInPastError,
    InvalidFieldError,
    InvalidStatusTransitionError,
    TaskListNotFoundError,
    TaskNotFoundError,
)
from app.domain.task_list import TaskList
from app.domain.value_objects import Priority, TaskStatus
from tests.unit.fakes import FakeUnitOfWork, FixedClock

_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_TODAY = date(2026, 1, 1)


async def _make_list(uow: FakeUnitOfWork, owner_id: object) -> TaskList:
    task_list = TaskList.create(
        owner_id=owner_id,  # type: ignore[arg-type]
        name="Groceries",
        description=None,
        now=_NOW,
    )
    await uow.task_lists.add(task_list)
    return task_list


async def test_create_task_succeeds_with_all_fields() -> None:
    uow = FakeUnitOfWork()
    actor_id = uuid4()
    task_list = await _make_list(uow, actor_id)
    use_case = CreateTask(uow, FixedClock(_NOW, _TODAY))

    result = await use_case.execute(
        CreateTaskCommand(
            actor_id=actor_id,
            list_id=task_list.id,
            title="Buy milk",
            description="2%",
            priority=Priority.LOW,
            due_date=_TODAY,
        )
    )

    assert result.title == "Buy milk"
    assert result.status == TaskStatus.PENDING
    stored = await uow.tasks.get(result.id)
    assert stored is not None


async def test_create_task_succeeds_with_due_date_omitted() -> None:
    uow = FakeUnitOfWork()
    actor_id = uuid4()
    task_list = await _make_list(uow, actor_id)
    use_case = CreateTask(uow, FixedClock(_NOW, _TODAY))

    result = await use_case.execute(
        CreateTaskCommand(
            actor_id=actor_id,
            list_id=task_list.id,
            title="Buy milk",
            description=None,
            priority=Priority.LOW,
            due_date=None,
        )
    )

    assert result.due_date is None


async def test_create_task_rejects_blank_title() -> None:
    uow = FakeUnitOfWork()
    actor_id = uuid4()
    task_list = await _make_list(uow, actor_id)
    use_case = CreateTask(uow, FixedClock(_NOW, _TODAY))

    with pytest.raises(InvalidFieldError):
        await use_case.execute(
            CreateTaskCommand(
                actor_id=actor_id,
                list_id=task_list.id,
                title="   ",
                description=None,
                priority=Priority.LOW,
                due_date=None,
            )
        )


async def test_create_task_rejects_title_over_200_characters() -> None:
    uow = FakeUnitOfWork()
    actor_id = uuid4()
    task_list = await _make_list(uow, actor_id)
    use_case = CreateTask(uow, FixedClock(_NOW, _TODAY))

    with pytest.raises(InvalidFieldError):
        await use_case.execute(
            CreateTaskCommand(
                actor_id=actor_id,
                list_id=task_list.id,
                title="x" * 201,
                description=None,
                priority=Priority.LOW,
                due_date=None,
            )
        )


async def test_create_task_rejects_description_over_2000_characters() -> None:
    uow = FakeUnitOfWork()
    actor_id = uuid4()
    task_list = await _make_list(uow, actor_id)
    use_case = CreateTask(uow, FixedClock(_NOW, _TODAY))

    with pytest.raises(InvalidFieldError):
        await use_case.execute(
            CreateTaskCommand(
                actor_id=actor_id,
                list_id=task_list.id,
                title="Buy milk",
                description="x" * 2001,
                priority=Priority.LOW,
                due_date=None,
            )
        )


async def test_create_task_in_foreign_list_raises_not_found() -> None:
    uow = FakeUnitOfWork()
    owner_id = uuid4()
    task_list = await _make_list(uow, owner_id)
    use_case = CreateTask(uow, FixedClock(_NOW, _TODAY))

    with pytest.raises(TaskListNotFoundError):
        await use_case.execute(
            CreateTaskCommand(
                actor_id=uuid4(),
                list_id=task_list.id,
                title="Buy milk",
                description=None,
                priority=Priority.LOW,
                due_date=None,
            )
        )


async def test_create_task_rejects_due_date_in_the_past() -> None:
    uow = FakeUnitOfWork()
    actor_id = uuid4()
    task_list = await _make_list(uow, actor_id)
    use_case = CreateTask(uow, FixedClock(_NOW, _TODAY))

    with pytest.raises(DueDateInPastError):
        await use_case.execute(
            CreateTaskCommand(
                actor_id=actor_id,
                list_id=task_list.id,
                title="Buy milk",
                description=None,
                priority=Priority.LOW,
                due_date=date(2025, 12, 31),
            )
        )


async def test_update_task_happy_path() -> None:
    uow = FakeUnitOfWork()
    actor_id = uuid4()
    task_list = await _make_list(uow, actor_id)
    create = CreateTask(uow, FixedClock(_NOW, _TODAY))
    task = await create.execute(
        CreateTaskCommand(
            actor_id=actor_id,
            list_id=task_list.id,
            title="Buy milk",
            description=None,
            priority=Priority.LOW,
            due_date=None,
        )
    )
    update = UpdateTask(uow, FixedClock(_NOW, _TODAY))

    result = await update.execute(
        UpdateTaskCommand(
            actor_id=actor_id,
            list_id=task_list.id,
            task_id=task.id,
            title="Updated title",
        )
    )

    assert result.title == "Updated title"


async def test_update_task_due_date_validated_only_when_patched() -> None:
    """An unrelated update on a task whose stored due_date has since
    passed must not fail (tasks spec: due_date validated only on patch)."""
    uow = FakeUnitOfWork()
    actor_id = uuid4()
    task_list = await _make_list(uow, actor_id)
    create = CreateTask(uow, FixedClock(_NOW, _TODAY))
    task = await create.execute(
        CreateTaskCommand(
            actor_id=actor_id,
            list_id=task_list.id,
            title="Buy milk",
            description=None,
            priority=Priority.LOW,
            due_date=_TODAY,
        )
    )
    # Time has moved on; the stored due_date is now in the past.
    later_today = date(2026, 1, 5)
    update = UpdateTask(uow, FixedClock(_NOW, later_today))

    result = await update.execute(
        UpdateTaskCommand(
            actor_id=actor_id,
            list_id=task_list.id,
            task_id=task.id,
            description="still fine",
        )
    )

    assert result.description == "still fine"
    assert result.due_date == _TODAY


async def test_update_task_rejects_due_date_in_the_past_when_patched() -> None:
    uow = FakeUnitOfWork()
    actor_id = uuid4()
    task_list = await _make_list(uow, actor_id)
    create = CreateTask(uow, FixedClock(_NOW, _TODAY))
    task = await create.execute(
        CreateTaskCommand(
            actor_id=actor_id,
            list_id=task_list.id,
            title="Buy milk",
            description=None,
            priority=Priority.LOW,
            due_date=None,
        )
    )
    update = UpdateTask(uow, FixedClock(_NOW, _TODAY))

    with pytest.raises(DueDateInPastError):
        await update.execute(
            UpdateTaskCommand(
                actor_id=actor_id,
                list_id=task_list.id,
                task_id=task.id,
                due_date=date(2025, 12, 31),
            )
        )


async def test_delete_task_removes_it_for_the_owner() -> None:
    uow = FakeUnitOfWork()
    actor_id = uuid4()
    task_list = await _make_list(uow, actor_id)
    create = CreateTask(uow, FixedClock(_NOW, _TODAY))
    task = await create.execute(
        CreateTaskCommand(
            actor_id=actor_id,
            list_id=task_list.id,
            title="Buy milk",
            description=None,
            priority=Priority.LOW,
            due_date=None,
        )
    )
    delete_use_case = DeleteTask(uow)

    await delete_use_case.execute(
        DeleteTaskCommand(actor_id=actor_id, list_id=task_list.id, task_id=task.id)
    )

    assert await uow.tasks.get(task.id) is None


@pytest.mark.parametrize(
    ("source", "destination"),
    [
        (TaskStatus.PENDING, TaskStatus.IN_PROGRESS),
        (TaskStatus.IN_PROGRESS, TaskStatus.PENDING),
        (TaskStatus.IN_PROGRESS, TaskStatus.DONE),
        (TaskStatus.DONE, TaskStatus.IN_PROGRESS),
    ],
)
async def test_change_task_status_allows_valid_transitions(
    source: TaskStatus, destination: TaskStatus
) -> None:
    uow = FakeUnitOfWork()
    actor_id = uuid4()
    task_list = await _make_list(uow, actor_id)
    create = CreateTask(uow, FixedClock(_NOW, _TODAY))
    task = await create.execute(
        CreateTaskCommand(
            actor_id=actor_id,
            list_id=task_list.id,
            title="Buy milk",
            description=None,
            priority=Priority.LOW,
            due_date=None,
        )
    )
    stored = await uow.tasks.get(task.id)
    assert stored is not None
    stored.status = source
    change_status = ChangeTaskStatus(uow, FixedClock(_NOW, _TODAY))

    result = await change_status.execute(
        ChangeTaskStatusCommand(
            actor_id=actor_id,
            list_id=task_list.id,
            task_id=task.id,
            status=destination,
        )
    )

    assert result.status == destination


@pytest.mark.parametrize(
    ("source", "destination"),
    [
        (TaskStatus.PENDING, TaskStatus.DONE),
        (TaskStatus.DONE, TaskStatus.PENDING),
        (TaskStatus.PENDING, TaskStatus.PENDING),
    ],
)
async def test_change_task_status_rejects_invalid_transitions(
    source: TaskStatus, destination: TaskStatus
) -> None:
    uow = FakeUnitOfWork()
    actor_id = uuid4()
    task_list = await _make_list(uow, actor_id)
    create = CreateTask(uow, FixedClock(_NOW, _TODAY))
    task = await create.execute(
        CreateTaskCommand(
            actor_id=actor_id,
            list_id=task_list.id,
            title="Buy milk",
            description=None,
            priority=Priority.LOW,
            due_date=None,
        )
    )
    stored = await uow.tasks.get(task.id)
    assert stored is not None
    stored.status = source
    change_status = ChangeTaskStatus(uow, FixedClock(_NOW, _TODAY))

    with pytest.raises(InvalidStatusTransitionError):
        await change_status.execute(
            ChangeTaskStatusCommand(
                actor_id=actor_id,
                list_id=task_list.id,
                task_id=task.id,
                status=destination,
            )
        )


async def test_non_owner_is_rejected_on_every_crud_and_status_action() -> None:
    """A stranger who does not own the list gets `TaskListNotFoundError`
    (the list-ownership check runs before task membership); both map to 404
    (tasks spec: non-owner access returns 404 in every case)."""
    uow = FakeUnitOfWork()
    actor_id = uuid4()
    stranger_id = uuid4()
    task_list = await _make_list(uow, actor_id)
    create = CreateTask(uow, FixedClock(_NOW, _TODAY))
    task = await create.execute(
        CreateTaskCommand(
            actor_id=actor_id,
            list_id=task_list.id,
            title="Buy milk",
            description=None,
            priority=Priority.LOW,
            due_date=None,
        )
    )

    with pytest.raises(TaskListNotFoundError):
        await GetTask(uow).execute(
            GetTaskCommand(actor_id=stranger_id, list_id=task_list.id, task_id=task.id)
        )

    with pytest.raises(TaskListNotFoundError):
        await UpdateTask(uow, FixedClock(_NOW, _TODAY)).execute(
            UpdateTaskCommand(
                actor_id=stranger_id,
                list_id=task_list.id,
                task_id=task.id,
                title="Hacked",
            )
        )

    with pytest.raises(TaskListNotFoundError):
        await DeleteTask(uow).execute(
            DeleteTaskCommand(
                actor_id=stranger_id, list_id=task_list.id, task_id=task.id
            )
        )

    with pytest.raises(TaskListNotFoundError):
        await ChangeTaskStatus(uow, FixedClock(_NOW, _TODAY)).execute(
            ChangeTaskStatusCommand(
                actor_id=stranger_id,
                list_id=task_list.id,
                task_id=task.id,
                status=TaskStatus.IN_PROGRESS,
            )
        )


async def test_get_task_from_a_different_list_raises_task_not_found() -> None:
    """Owner-owned task from a *different* list -> `TaskNotFoundError`
    (tasks spec: task must belong to the path's list_id, never 403)."""
    uow = FakeUnitOfWork()
    actor_id = uuid4()
    task_list = await _make_list(uow, actor_id)
    other_list = TaskList.create(
        owner_id=actor_id, name="Work", description=None, now=_NOW
    )
    await uow.task_lists.add(other_list)
    create = CreateTask(uow, FixedClock(_NOW, _TODAY))
    task = await create.execute(
        CreateTaskCommand(
            actor_id=actor_id,
            list_id=other_list.id,
            title="Unrelated",
            description=None,
            priority=Priority.LOW,
            due_date=None,
        )
    )

    with pytest.raises(TaskNotFoundError):
        await GetTask(uow).execute(
            GetTaskCommand(actor_id=actor_id, list_id=task_list.id, task_id=task.id)
        )


async def test_get_task_scoped_to_owner() -> None:
    uow = FakeUnitOfWork()
    actor_id = uuid4()
    task_list = await _make_list(uow, actor_id)
    create = CreateTask(uow, FixedClock(_NOW, _TODAY))
    task = await create.execute(
        CreateTaskCommand(
            actor_id=actor_id,
            list_id=task_list.id,
            title="Buy milk",
            description=None,
            priority=Priority.LOW,
            due_date=None,
        )
    )
    get_use_case = GetTask(uow)

    result = await get_use_case.execute(
        GetTaskCommand(actor_id=actor_id, list_id=task_list.id, task_id=task.id)
    )
    assert result.id == task.id
