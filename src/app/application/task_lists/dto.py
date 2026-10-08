"""Commands for the task-list use cases (design ADR-04).

Every command carries `actor_id`. Results are the `TaskList` domain entity
itself (ADR-04: a dedicated result dataclass is reserved for composite
results, which no task-list use case needs).
"""

from dataclasses import dataclass
from uuid import UUID

from app.application.common import UNSET, Unset


@dataclass(frozen=True, slots=True)
class CreateTaskListCommand:
    actor_id: UUID
    name: str
    description: str | None


@dataclass(frozen=True, slots=True)
class GetTaskListCommand:
    actor_id: UUID
    list_id: UUID


@dataclass(frozen=True, slots=True)
class ListTaskListsCommand:
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class UpdateTaskListCommand:
    actor_id: UUID
    list_id: UUID
    # `name` cannot be cleared (it is a required field): `None` is an
    # invalid value handled explicitly by `UpdateTaskList`, never confused
    # with `UNSET` (field omitted from the PATCH body).
    name: str | None | Unset = UNSET
    description: str | None | Unset = UNSET


@dataclass(frozen=True, slots=True)
class DeleteTaskListCommand:
    actor_id: UUID
    list_id: UUID
