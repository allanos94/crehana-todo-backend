"""Commands for the assignment use cases (design ADR-04, ADR-12).

Every command carries `actor_id`. `AssignTask`'s result is the `Task`
entity itself (same shape as `ChangeTaskStatus`); `ListMyAssignedTasks`
needs the composite `AssignedTaskPage` to pair its page with `total`.
"""

from dataclasses import dataclass
from uuid import UUID

from app.domain.task import Task


@dataclass(frozen=True, slots=True)
class AssignTaskCommand:
    actor_id: UUID
    list_id: UUID
    task_id: UUID
    assignee_id: UUID | None


@dataclass(frozen=True, slots=True)
class ListMyAssignedTasksCommand:
    actor_id: UUID
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class AssignedTaskPage:
    items: list[Task]
    total: int
