"""Commands for the task use cases (design ADR-04).

Every command carries `actor_id`. `UpdateTaskCommand` is `UNSET`-aware so
`UpdateTask` only touches fields the client actually patched (ADR-04: this
is also why `due_date` is only re-validated when it is present in the
patch). Results are the `Task` domain entity itself for every use case
except `ListTasks`, whose composite `TaskPage` result pairs the filtered
page with the list-wide `completion_percentage` (design ADR-10).
"""

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from app.application.common import UNSET, Unset
from app.domain.task import Task
from app.domain.value_objects import Priority, TaskStatus


@dataclass(frozen=True, slots=True)
class CreateTaskCommand:
    actor_id: UUID
    list_id: UUID
    title: str
    description: str | None
    priority: Priority
    due_date: date | None


@dataclass(frozen=True, slots=True)
class GetTaskCommand:
    actor_id: UUID
    list_id: UUID
    task_id: UUID


@dataclass(frozen=True, slots=True)
class UpdateTaskCommand:
    actor_id: UUID
    list_id: UUID
    task_id: UUID
    # `title` cannot be cleared (it is a required field): `None` is an
    # invalid value handled explicitly by `UpdateTask`, never confused with
    # `UNSET` (field omitted from the PATCH body).
    title: str | None | Unset = UNSET
    description: str | None | Unset = UNSET
    priority: Priority | Unset = UNSET
    due_date: date | None | Unset = UNSET


@dataclass(frozen=True, slots=True)
class DeleteTaskCommand:
    actor_id: UUID
    list_id: UUID
    task_id: UUID


@dataclass(frozen=True, slots=True)
class ChangeTaskStatusCommand:
    actor_id: UUID
    list_id: UUID
    task_id: UUID
    status: TaskStatus


@dataclass(frozen=True, slots=True)
class ListTasksCommand:
    actor_id: UUID
    list_id: UUID
    status: TaskStatus | None
    priority: Priority | None
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class TaskPage:
    """`items`/`total` reflect `ListTasksCommand`'s filters and pagination;
    `completion_percentage` never does (design ADR-10, tasks spec)."""

    items: list[Task]
    total: int
    completion_percentage: float
