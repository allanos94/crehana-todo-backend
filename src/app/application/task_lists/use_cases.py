"""Task-list use cases (task-lists spec): owner-scoped CRUD with per-owner,
case-insensitive name uniqueness checked here for a friendly 409 (the DB's
functional unique index, shipped in slice 2b, backs this for race safety).
"""

from uuid import UUID

from app.application.authorization import AccessPolicy
from app.application.common import UNSET
from app.application.ports import Clock, UnitOfWork
from app.application.task_lists.dto import (
    CreateTaskListCommand,
    DeleteTaskListCommand,
    GetTaskListCommand,
    ListTaskListsCommand,
    UpdateTaskListCommand,
)
from app.domain.exceptions import DuplicateTaskListNameError, InvalidFieldError
from app.domain.task_list import TaskList


async def _ensure_name_available(
    uow: UnitOfWork,
    owner_id: UUID,
    name: str,
    *,
    exclude_id: UUID | None = None,
) -> None:
    """Raise `DuplicateTaskListNameError` if `owner_id` already has a list
    with `name`, compared case-insensitively (task-lists spec: per-owner
    case-insensitive uniqueness). Shared by `CreateTaskList`/`UpdateTaskList`."""
    if await uow.task_lists.name_exists(owner_id, name, exclude_id=exclude_id):
        raise DuplicateTaskListNameError()


class CreateTaskList:
    """Create a new owner-scoped `TaskList` (task-lists spec: creation,
    field validation, per-owner uniqueness)."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    async def execute(self, command: CreateTaskListCommand) -> TaskList:
        task_list = TaskList.create(
            owner_id=command.actor_id,
            name=command.name,
            description=command.description,
            now=self._clock.now(),
        )
        async with self._uow:
            await _ensure_name_available(self._uow, command.actor_id, task_list.name)
            await self._uow.task_lists.add(task_list)
            await self._uow.commit()
        return task_list


class ListTaskLists:
    """List every `TaskList` owned by the actor (task-lists spec: retrieval)."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def execute(self, command: ListTaskListsCommand) -> list[TaskList]:
        async with self._uow:
            return await self._uow.task_lists.list_by_owner(command.actor_id)


class GetTaskList:
    """Fetch one owner-scoped `TaskList` (task-lists spec: retrieval;
    non-owner/nonexistent both -> 404, never 403)."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def execute(self, command: GetTaskListCommand) -> TaskList:
        async with self._uow:
            policy = AccessPolicy(self._uow)
            return await policy.owned_list(command.list_id, command.actor_id)


class UpdateTaskList:
    """Rename/describe an owner-scoped `TaskList` (task-lists spec: update,
    same validation/uniqueness rules as creation, self-rename excluded)."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    async def execute(self, command: UpdateTaskListCommand) -> TaskList:
        async with self._uow:
            policy = AccessPolicy(self._uow)
            task_list = await policy.owned_list(command.list_id, command.actor_id)
            now = self._clock.now()
            if command.name is not UNSET:
                if command.name is None:
                    raise InvalidFieldError("name", "name must not be blank")
                task_list.rename(command.name, now)
                await _ensure_name_available(
                    self._uow,
                    command.actor_id,
                    task_list.name,
                    exclude_id=task_list.id,
                )
            if command.description is not UNSET:
                task_list.describe(command.description, now)
            await self._uow.task_lists.update(task_list)
            await self._uow.commit()
        return task_list


class DeleteTaskList:
    """Delete an owner-scoped `TaskList` (task-lists spec: delete cascades
    its tasks at the DB level, non-owner -> 404)."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def execute(self, command: DeleteTaskListCommand) -> None:
        async with self._uow:
            policy = AccessPolicy(self._uow)
            task_list = await policy.owned_list(command.list_id, command.actor_id)
            await self._uow.task_lists.delete(task_list.id)
            await self._uow.commit()
