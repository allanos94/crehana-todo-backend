"""Assignment use cases (task-assignment spec): owner-only assign/unassign
with a post-commit-only fake invitation (design ADR-12), and the
assignee's own cross-list visibility.
"""

from app.application.assignment.dto import (
    AssignedTaskPage,
    AssignTaskCommand,
    ListMyAssignedTasksCommand,
)
from app.application.authorization import AccessPolicy
from app.application.ports import Clock, NotificationService, TaskInvitation, UnitOfWork
from app.domain.exceptions import AssigneeNotFoundError
from app.domain.task import Task


class AssignTask:
    """Set or clear a task's assignee (owner-only). Notifies the new
    assignee only after a successful commit, and only when the assignee
    actually changes to a new, non-null user (design ADR-12): unassigning
    (`assignee_id=None`) never notifies, and reassigning notifies only the
    new assignee, not the old one."""

    def __init__(
        self, uow: UnitOfWork, clock: Clock, notifier: NotificationService
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._notifier = notifier

    async def execute(self, command: AssignTaskCommand) -> Task:
        async with self._uow:
            policy = AccessPolicy(self._uow)
            task = await policy.owned_task(
                command.list_id, command.task_id, command.actor_id
            )
            task_list = await self._uow.task_lists.get(command.list_id)
            assert task_list is not None
            owner = await self._uow.users.get_by_id(task_list.owner_id)
            assert owner is not None

            previous_assignee_id = task.assignee_id
            new_assignee_email: str | None = None
            if command.assignee_id is not None:
                new_assignee = await self._uow.users.get_by_id(command.assignee_id)
                if new_assignee is None:
                    raise AssigneeNotFoundError()
                new_assignee_email = new_assignee.email

            task.assign(command.assignee_id, self._clock.now())
            await self._uow.tasks.update(task)
            await self._uow.commit()

            should_notify = (
                command.assignee_id is not None
                and command.assignee_id != previous_assignee_id
            )
            if should_notify:
                assert new_assignee_email is not None
                await self._notifier.send_task_invitation(
                    TaskInvitation(
                        to_email=new_assignee_email,
                        task_title=task.title,
                        list_name=task_list.name,
                        invited_by_email=owner.email,
                    )
                )
        return task


class ListMyAssignedTasks:
    """List tasks currently assigned to the caller, across every list
    regardless of who owns it (task-assignment spec: the owner of a list
    is never implicitly an assignee of its tasks)."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def execute(self, command: ListMyAssignedTasksCommand) -> AssignedTaskPage:
        async with self._uow:
            items, total = await self._uow.tasks.list_by_assignee(
                command.actor_id, command.limit, command.offset
            )
        return AssignedTaskPage(items=items, total=total)
