"""The single application-layer authorization policy (design ADR-06).

Resolves owner/non-owner/missing-resource access. Every method is called
from inside an already-open `async with uow:` block (the use case owns the
transaction), and every failure raises the exact `NotFoundError` concrete
type the HTTP layer maps to 404 -- never 403, so a stranger and a missing
resource are indistinguishable to the caller.

`status_changeable_task` is added by a later slice (5).
"""

from uuid import UUID

from app.application.ports import UnitOfWork
from app.domain.exceptions import TaskListNotFoundError, TaskNotFoundError
from app.domain.task import Task
from app.domain.task_list import TaskList


class AccessPolicy:
    """Resolves actor access to owner-scoped resources."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def owned_list(self, list_id: UUID, actor_id: UUID) -> TaskList:
        """Return the `TaskList` if `actor_id` owns it; otherwise raise
        `TaskListNotFoundError` (404), identically for a missing list and
        for a list owned by someone else."""
        task_list = await self._uow.task_lists.get(list_id)
        if task_list is None or task_list.owner_id != actor_id:
            raise TaskListNotFoundError()
        return task_list

    async def owned_task(self, list_id: UUID, task_id: UUID, actor_id: UUID) -> Task:
        """Return the `Task` if `actor_id` owns its list and the task
        belongs to `list_id`. Checks list ownership first (`TaskListNotFoundError`),
        then task membership (`TaskNotFoundError`) -- a missing list, a
        missing task, and a task from a different list all look the same
        to the caller (tasks spec: non-owner/nonexistent -> 404)."""
        await self.owned_list(list_id, actor_id)
        task = await self._uow.tasks.get(task_id)
        if task is None or task.list_id != list_id:
            raise TaskNotFoundError()
        return task
