"""The single application-layer authorization policy (design ADR-06).

Resolves owner/non-owner/missing-resource access. Every method is called
from inside an already-open `async with uow:` block (the use case owns the
transaction), and every failure raises the exact `NotFoundError` concrete
type the HTTP layer maps to 404 -- never 403, so a stranger and a missing
resource are indistinguishable to the caller.

`owned_task` and `status_changeable_task` are added by later slices (3a/5).
"""

from uuid import UUID

from app.application.ports import UnitOfWork
from app.domain.exceptions import TaskListNotFoundError
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
