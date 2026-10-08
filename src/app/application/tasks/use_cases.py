"""Task use cases (tasks spec): owner-scoped CRUD and status changes.

`ChangeTaskStatus` here is the owner-only path (`AccessPolicy.owned_task`);
the assignee path (`AccessPolicy.status_changeable_task`) replaces it in
Phase 8 once assignment lands.
"""

from app.application.authorization import AccessPolicy
from app.application.common import UNSET
from app.application.ports import Clock, UnitOfWork
from app.application.tasks.dto import (
    ChangeTaskStatusCommand,
    CreateTaskCommand,
    DeleteTaskCommand,
    GetTaskCommand,
    UpdateTaskCommand,
)
from app.domain.exceptions import InvalidFieldError
from app.domain.task import Task


class CreateTask:
    """Create a new `Task` inside an owned `TaskList` (tasks spec: creation,
    field validation, due_date-not-past)."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    async def execute(self, command: CreateTaskCommand) -> Task:
        async with self._uow:
            policy = AccessPolicy(self._uow)
            await policy.owned_list(command.list_id, command.actor_id)
            task = Task.create(
                list_id=command.list_id,
                title=command.title,
                description=command.description,
                priority=command.priority,
                due_date=command.due_date,
                today=self._clock.today(),
                now=self._clock.now(),
            )
            await self._uow.tasks.add(task)
            await self._uow.commit()
        return task


class GetTask:
    """Fetch one owner-scoped `Task` (tasks spec: retrieval; non-owner and
    nonexistent both -> 404)."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def execute(self, command: GetTaskCommand) -> Task:
        async with self._uow:
            policy = AccessPolicy(self._uow)
            return await policy.owned_task(
                command.list_id, command.task_id, command.actor_id
            )


class UpdateTask:
    """Update an owner-scoped `Task` (tasks spec: update, same validation
    rules as creation, due_date re-validated only when patched)."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    async def execute(self, command: UpdateTaskCommand) -> Task:
        async with self._uow:
            policy = AccessPolicy(self._uow)
            task = await policy.owned_task(
                command.list_id, command.task_id, command.actor_id
            )
            now = self._clock.now()
            if command.title is not UNSET:
                if command.title is None:
                    raise InvalidFieldError("title", "title must not be blank")
                task.rename(command.title, now)
            if command.description is not UNSET:
                task.describe(command.description, now)
            if command.priority is not UNSET:
                task.set_priority(command.priority, now)
            if command.due_date is not UNSET:
                task.reschedule(command.due_date, self._clock.today(), now)
            await self._uow.tasks.update(task)
            await self._uow.commit()
        return task


class DeleteTask:
    """Delete an owner-scoped `Task` (tasks spec: delete; non-owner -> 404)."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def execute(self, command: DeleteTaskCommand) -> None:
        async with self._uow:
            policy = AccessPolicy(self._uow)
            task = await policy.owned_task(
                command.list_id, command.task_id, command.actor_id
            )
            await self._uow.tasks.delete(task.id)
            await self._uow.commit()


class ChangeTaskStatus:
    """Change an owner-scoped `Task`'s status (tasks spec: strict state
    machine; owner path only -- see module docstring)."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    async def execute(self, command: ChangeTaskStatusCommand) -> Task:
        async with self._uow:
            policy = AccessPolicy(self._uow)
            task = await policy.owned_task(
                command.list_id, command.task_id, command.actor_id
            )
            task.change_status(command.status, self._clock.now())
            await self._uow.tasks.update(task)
            await self._uow.commit()
        return task
