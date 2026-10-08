"""Unit tests for the assignment use cases against in-memory fakes plus a
`RecordingNotifier` (task-assignment spec: assign/unassign/reassign, the
post-commit-only notification rule, and `/users/me/tasks` visibility).
"""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from app.application.assignment.dto import (
    AssignTaskCommand,
    ListMyAssignedTasksCommand,
)
from app.application.assignment.use_cases import AssignTask, ListMyAssignedTasks
from app.application.tasks.dto import CreateTaskCommand
from app.application.tasks.use_cases import CreateTask
from app.domain.exceptions import AssigneeNotFoundError, TaskListNotFoundError
from app.domain.task_list import TaskList
from app.domain.user import User
from app.domain.value_objects import Priority
from tests.unit.fakes import FakeUnitOfWork, FixedClock, RecordingNotifier

_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_TODAY = date(2026, 1, 1)


async def _make_owner_list_and_task(
    uow: FakeUnitOfWork,
) -> tuple[User, TaskList, object]:
    owner = User.create(email="owner@example.com", hashed_password="x", now=_NOW)
    await uow.users.add(owner)
    task_list = TaskList.create(
        owner_id=owner.id, name="Groceries", description=None, now=_NOW
    )
    await uow.task_lists.add(task_list)
    create = CreateTask(uow, FixedClock(_NOW, _TODAY))
    task = await create.execute(
        CreateTaskCommand(
            actor_id=owner.id,
            list_id=task_list.id,
            title="Buy milk",
            description=None,
            priority=Priority.LOW,
            due_date=None,
        )
    )
    return owner, task_list, task


class _FailingOnCommitUnitOfWork(FakeUnitOfWork):
    """A `FakeUnitOfWork` whose `commit()` always raises, to prove a
    notification is never recorded when the commit fails (ADR-12)."""

    async def commit(self) -> None:
        raise RuntimeError("simulated commit failure")


async def test_owner_assigns_task_to_a_registered_user() -> None:
    uow = FakeUnitOfWork()
    owner, task_list, task = await _make_owner_list_and_task(uow)
    assignee = User.create(email="assignee@example.com", hashed_password="x", now=_NOW)
    await uow.users.add(assignee)
    notifier = RecordingNotifier()
    use_case = AssignTask(uow, FixedClock(_NOW, _TODAY), notifier)

    result = await use_case.execute(
        AssignTaskCommand(
            actor_id=owner.id,
            list_id=task_list.id,
            task_id=task.id,
            assignee_id=assignee.id,
        )
    )

    assert result.assignee_id == assignee.id
    assert len(notifier.sent) == 1
    assert notifier.sent[0].to_email == "assignee@example.com"


async def test_assign_to_nonexistent_user_raises_assignee_not_found() -> None:
    uow = FakeUnitOfWork()
    owner, task_list, task = await _make_owner_list_and_task(uow)
    notifier = RecordingNotifier()
    use_case = AssignTask(uow, FixedClock(_NOW, _TODAY), notifier)

    with pytest.raises(AssigneeNotFoundError):
        await use_case.execute(
            AssignTaskCommand(
                actor_id=owner.id,
                list_id=task_list.id,
                task_id=task.id,
                assignee_id=uuid4(),
            )
        )
    assert notifier.sent == []


async def test_non_owner_cannot_assign() -> None:
    """A stranger who does not own the list gets `TaskListNotFoundError`
    (`AssignTask` uses `owned_task`, the same owner-only policy as every
    other CRUD action -- the same ADR-06 distinction already documented
    for Phase 5/6's non-owner tests); it maps to 404 over HTTP."""
    uow = FakeUnitOfWork()
    owner, task_list, task = await _make_owner_list_and_task(uow)
    assignee = User.create(email="assignee@example.com", hashed_password="x", now=_NOW)
    await uow.users.add(assignee)
    stranger_id = uuid4()
    notifier = RecordingNotifier()
    use_case = AssignTask(uow, FixedClock(_NOW, _TODAY), notifier)

    with pytest.raises(TaskListNotFoundError):
        await use_case.execute(
            AssignTaskCommand(
                actor_id=stranger_id,
                list_id=task_list.id,
                task_id=task.id,
                assignee_id=assignee.id,
            )
        )
    assert notifier.sent == []


async def test_owner_unassigns_without_a_notification() -> None:
    uow = FakeUnitOfWork()
    owner, task_list, task = await _make_owner_list_and_task(uow)
    assignee = User.create(email="assignee@example.com", hashed_password="x", now=_NOW)
    await uow.users.add(assignee)
    notifier = RecordingNotifier()
    use_case = AssignTask(uow, FixedClock(_NOW, _TODAY), notifier)
    await use_case.execute(
        AssignTaskCommand(
            actor_id=owner.id,
            list_id=task_list.id,
            task_id=task.id,
            assignee_id=assignee.id,
        )
    )
    notifier.sent.clear()

    result = await use_case.execute(
        AssignTaskCommand(
            actor_id=owner.id,
            list_id=task_list.id,
            task_id=task.id,
            assignee_id=None,
        )
    )

    assert result.assignee_id is None
    assert notifier.sent == []


async def test_reassignment_notifies_only_the_new_assignee() -> None:
    uow = FakeUnitOfWork()
    owner, task_list, task = await _make_owner_list_and_task(uow)
    old_assignee = User.create(email="old@example.com", hashed_password="x", now=_NOW)
    new_assignee = User.create(email="new@example.com", hashed_password="x", now=_NOW)
    await uow.users.add(old_assignee)
    await uow.users.add(new_assignee)
    notifier = RecordingNotifier()
    use_case = AssignTask(uow, FixedClock(_NOW, _TODAY), notifier)
    await use_case.execute(
        AssignTaskCommand(
            actor_id=owner.id,
            list_id=task_list.id,
            task_id=task.id,
            assignee_id=old_assignee.id,
        )
    )
    notifier.sent.clear()

    result = await use_case.execute(
        AssignTaskCommand(
            actor_id=owner.id,
            list_id=task_list.id,
            task_id=task.id,
            assignee_id=new_assignee.id,
        )
    )

    assert result.assignee_id == new_assignee.id
    assert len(notifier.sent) == 1
    assert notifier.sent[0].to_email == "new@example.com"


async def test_notification_recorded_only_after_successful_commit() -> None:
    setup_uow = FakeUnitOfWork()
    owner, task_list, task = await _make_owner_list_and_task(setup_uow)
    assignee = User.create(email="assignee@example.com", hashed_password="x", now=_NOW)
    await setup_uow.users.add(assignee)
    # Reuse the same (already-populated) repositories under a UnitOfWork
    # whose `commit()` always raises, so only `AssignTask`'s own commit
    # fails -- the setup above must succeed first.
    failing_uow = _FailingOnCommitUnitOfWork(
        users=setup_uow.users,
        task_lists=setup_uow.task_lists,
        tasks=setup_uow.tasks,
    )
    notifier = RecordingNotifier()
    use_case = AssignTask(failing_uow, FixedClock(_NOW, _TODAY), notifier)

    with pytest.raises(RuntimeError):
        await use_case.execute(
            AssignTaskCommand(
                actor_id=owner.id,
                list_id=task_list.id,
                task_id=task.id,
                assignee_id=assignee.id,
            )
        )

    assert notifier.sent == []


async def test_list_my_assigned_tasks_returns_only_the_callers_tasks() -> None:
    uow = FakeUnitOfWork()
    owner, list_a, task_a = await _make_owner_list_and_task(uow)
    list_b = TaskList.create(owner_id=owner.id, name="Work", description=None, now=_NOW)
    await uow.task_lists.add(list_b)
    create = CreateTask(uow, FixedClock(_NOW, _TODAY))
    task_b = await create.execute(
        CreateTaskCommand(
            actor_id=owner.id,
            list_id=list_b.id,
            title="Unrelated",
            description=None,
            priority=Priority.LOW,
            due_date=None,
        )
    )
    assignee = User.create(email="assignee@example.com", hashed_password="x", now=_NOW)
    await uow.users.add(assignee)
    notifier = RecordingNotifier()
    assign = AssignTask(uow, FixedClock(_NOW, _TODAY), notifier)
    await assign.execute(
        AssignTaskCommand(
            actor_id=owner.id,
            list_id=list_a.id,
            task_id=task_a.id,
            assignee_id=assignee.id,
        )
    )
    use_case = ListMyAssignedTasks(uow)

    result = await use_case.execute(
        ListMyAssignedTasksCommand(actor_id=assignee.id, limit=20, offset=0)
    )

    assert [item.id for item in result.items] == [task_a.id]
    assert task_b.id not in [item.id for item in result.items]
    assert result.total == 1


async def test_owner_is_not_implicitly_an_assignee() -> None:
    uow = FakeUnitOfWork()
    owner, task_list, task = await _make_owner_list_and_task(uow)
    use_case = ListMyAssignedTasks(uow)

    result = await use_case.execute(
        ListMyAssignedTasksCommand(actor_id=owner.id, limit=20, offset=0)
    )

    assert result.items == []
    assert result.total == 0


async def test_list_my_assigned_tasks_empty_for_a_user_with_none_assigned() -> None:
    uow = FakeUnitOfWork()
    stranger_id = uuid4()
    use_case = ListMyAssignedTasks(uow)

    result = await use_case.execute(
        ListMyAssignedTasksCommand(actor_id=stranger_id, limit=20, offset=0)
    )

    assert result.items == []
    assert result.total == 0
