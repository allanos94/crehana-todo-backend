"""Unit tests for the task-list use cases against in-memory fakes
(task-lists spec: CRUD, per-owner case-insensitive name uniqueness,
self-rename exclusion, owner-scoped retrieval/listing).
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.application.task_lists.dto import (
    CreateTaskListCommand,
    DeleteTaskListCommand,
    GetTaskListCommand,
    ListTaskListsCommand,
    UpdateTaskListCommand,
)
from app.application.task_lists.use_cases import (
    CreateTaskList,
    DeleteTaskList,
    GetTaskList,
    ListTaskLists,
    UpdateTaskList,
)
from app.domain.exceptions import (
    DuplicateTaskListNameError,
    InvalidFieldError,
    TaskListNotFoundError,
)
from tests.unit.fakes import FakeUnitOfWork, FixedClock

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def test_create_task_list_succeeds() -> None:
    uow = FakeUnitOfWork()
    actor_id = uuid4()
    use_case = CreateTaskList(uow, FixedClock(_NOW))

    result = await use_case.execute(
        CreateTaskListCommand(actor_id=actor_id, name="Groceries", description=None)
    )

    assert result.name == "Groceries"
    stored = await uow.task_lists.get(result.id)
    assert stored is not None


async def test_create_task_list_rejects_duplicate_name_same_case() -> None:
    uow = FakeUnitOfWork()
    actor_id = uuid4()
    use_case = CreateTaskList(uow, FixedClock(_NOW))
    await use_case.execute(
        CreateTaskListCommand(actor_id=actor_id, name="Groceries", description=None)
    )

    with pytest.raises(DuplicateTaskListNameError):
        await use_case.execute(
            CreateTaskListCommand(actor_id=actor_id, name="Groceries", description=None)
        )


async def test_create_task_list_rejects_duplicate_name_different_case() -> None:
    uow = FakeUnitOfWork()
    actor_id = uuid4()
    use_case = CreateTaskList(uow, FixedClock(_NOW))
    await use_case.execute(
        CreateTaskListCommand(actor_id=actor_id, name="Groceries", description=None)
    )

    with pytest.raises(DuplicateTaskListNameError):
        await use_case.execute(
            CreateTaskListCommand(actor_id=actor_id, name="GROCERIES", description=None)
        )


async def test_create_task_list_allows_same_name_across_different_owners() -> None:
    uow = FakeUnitOfWork()
    use_case = CreateTaskList(uow, FixedClock(_NOW))
    await use_case.execute(
        CreateTaskListCommand(actor_id=uuid4(), name="Groceries", description=None)
    )

    result = await use_case.execute(
        CreateTaskListCommand(actor_id=uuid4(), name="Groceries", description=None)
    )

    assert result.name == "Groceries"


async def test_update_task_list_renaming_into_a_conflicting_name_raises() -> None:
    uow = FakeUnitOfWork()
    actor_id = uuid4()
    create = CreateTaskList(uow, FixedClock(_NOW))
    await create.execute(
        CreateTaskListCommand(actor_id=actor_id, name="Work", description=None)
    )
    personal = await create.execute(
        CreateTaskListCommand(actor_id=actor_id, name="Personal", description=None)
    )
    update = UpdateTaskList(uow, FixedClock(_NOW))

    with pytest.raises(DuplicateTaskListNameError):
        await update.execute(
            UpdateTaskListCommand(actor_id=actor_id, list_id=personal.id, name="Work")
        )


async def test_update_task_list_renaming_excludes_its_own_id() -> None:
    uow = FakeUnitOfWork()
    actor_id = uuid4()
    create = CreateTaskList(uow, FixedClock(_NOW))
    task_list = await create.execute(
        CreateTaskListCommand(actor_id=actor_id, name="Work", description=None)
    )
    update = UpdateTaskList(uow, FixedClock(_NOW))

    result = await update.execute(
        UpdateTaskListCommand(actor_id=actor_id, list_id=task_list.id, name="work")
    )

    assert result.name == "work"


async def test_update_task_list_rejects_invalid_field() -> None:
    uow = FakeUnitOfWork()
    actor_id = uuid4()
    create = CreateTaskList(uow, FixedClock(_NOW))
    task_list = await create.execute(
        CreateTaskListCommand(actor_id=actor_id, name="Work", description=None)
    )
    update = UpdateTaskList(uow, FixedClock(_NOW))

    with pytest.raises(InvalidFieldError):
        await update.execute(
            UpdateTaskListCommand(actor_id=actor_id, list_id=task_list.id, name="   ")
        )


async def test_update_task_list_rejects_non_owner() -> None:
    uow = FakeUnitOfWork()
    actor_id = uuid4()
    create = CreateTaskList(uow, FixedClock(_NOW))
    task_list = await create.execute(
        CreateTaskListCommand(actor_id=actor_id, name="Work", description=None)
    )
    update = UpdateTaskList(uow, FixedClock(_NOW))

    with pytest.raises(TaskListNotFoundError):
        await update.execute(
            UpdateTaskListCommand(actor_id=uuid4(), list_id=task_list.id, name="Hacked")
        )


async def test_get_task_list_scoped_to_owner() -> None:
    uow = FakeUnitOfWork()
    actor_id = uuid4()
    create = CreateTaskList(uow, FixedClock(_NOW))
    task_list = await create.execute(
        CreateTaskListCommand(actor_id=actor_id, name="Work", description=None)
    )
    get_use_case = GetTaskList(uow)

    result = await get_use_case.execute(
        GetTaskListCommand(actor_id=actor_id, list_id=task_list.id)
    )
    assert result.id == task_list.id

    with pytest.raises(TaskListNotFoundError):
        await get_use_case.execute(
            GetTaskListCommand(actor_id=uuid4(), list_id=task_list.id)
        )


async def test_list_task_lists_scoped_to_owner() -> None:
    uow = FakeUnitOfWork()
    owner_id = uuid4()
    other_owner_id = uuid4()
    create = CreateTaskList(uow, FixedClock(_NOW))
    await create.execute(
        CreateTaskListCommand(actor_id=owner_id, name="Work", description=None)
    )
    await create.execute(
        CreateTaskListCommand(actor_id=owner_id, name="Personal", description=None)
    )
    await create.execute(
        CreateTaskListCommand(
            actor_id=other_owner_id, name="Other owner's list", description=None
        )
    )
    list_use_case = ListTaskLists(uow)

    results = await list_use_case.execute(ListTaskListsCommand(actor_id=owner_id))

    assert {task_list.name for task_list in results} == {"Work", "Personal"}


async def test_delete_task_list_removes_it_for_the_owner() -> None:
    uow = FakeUnitOfWork()
    actor_id = uuid4()
    create = CreateTaskList(uow, FixedClock(_NOW))
    task_list = await create.execute(
        CreateTaskListCommand(actor_id=actor_id, name="Work", description=None)
    )
    delete_use_case = DeleteTaskList(uow)

    await delete_use_case.execute(
        DeleteTaskListCommand(actor_id=actor_id, list_id=task_list.id)
    )

    assert await uow.task_lists.get(task_list.id) is None


async def test_delete_task_list_rejects_non_owner() -> None:
    uow = FakeUnitOfWork()
    actor_id = uuid4()
    create = CreateTaskList(uow, FixedClock(_NOW))
    task_list = await create.execute(
        CreateTaskListCommand(actor_id=actor_id, name="Work", description=None)
    )
    delete_use_case = DeleteTaskList(uow)

    with pytest.raises(TaskListNotFoundError):
        await delete_use_case.execute(
            DeleteTaskListCommand(actor_id=uuid4(), list_id=task_list.id)
        )
