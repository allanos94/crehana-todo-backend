"""Repository Protocols (design ADR-05).

Repositories are `typing.Protocol`s so fakes satisfy them structurally,
without inheritance. `TaskRepository` carries basic CRUD plus filtered,
paginated `search` (slice 4); `list_by_assignee` lands in slice 5.
"""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.domain.task import Task
from app.domain.task_list import TaskList
from app.domain.user import User
from app.domain.value_objects import Priority, TaskStatus


@dataclass(frozen=True, slots=True)
class TaskFilter:
    """Optional `status`/`priority` filters applied to a listing's `items`
    and `total` -- never to the `completion_percentage` count, which is
    always computed over every task in the list (design ADR-10)."""

    status: TaskStatus | None = None
    priority: Priority | None = None


@dataclass(frozen=True, slots=True)
class TaskCounts:
    """The three counts `TaskRepository.search` returns alongside a page
    of items (design ADR-10): `total_all`/`done_all` back
    `completion_percentage` (filter-independent), `total_filtered` is the
    listing's `total` (reflects `TaskFilter`, not the page size)."""

    total_all: int
    done_all: int
    total_filtered: int


class UserRepository(Protocol):
    async def add(self, user: User) -> None: ...

    async def get_by_id(self, user_id: UUID) -> User | None: ...

    async def get_by_email(self, email: str) -> User | None: ...


class TaskListRepository(Protocol):
    async def add(self, task_list: TaskList) -> None: ...

    async def update(self, task_list: TaskList) -> None: ...

    async def get(self, list_id: UUID) -> TaskList | None: ...

    async def list_by_owner(self, owner_id: UUID) -> list[TaskList]: ...

    async def name_exists(
        self, owner_id: UUID, name: str, exclude_id: UUID | None = None
    ) -> bool: ...

    async def delete(self, list_id: UUID) -> None: ...


class TaskRepository(Protocol):
    async def add(self, task: Task) -> None: ...

    async def update(self, task: Task) -> None: ...

    async def get(self, task_id: UUID) -> Task | None: ...

    async def delete(self, task_id: UUID) -> None: ...

    async def search(
        self, list_id: UUID, filters: TaskFilter, limit: int, offset: int
    ) -> tuple[list[Task], TaskCounts]: ...
