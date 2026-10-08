"""Repository Protocols (design ADR-05).

Repositories are `typing.Protocol`s so fakes satisfy them structurally,
without inheritance. `TaskRepository` now carries basic CRUD (slice 3a);
filters/counts (`TaskFilter`, `TaskCounts`, `search`) and `list_by_assignee`
land in later slices (4, 5).
"""

from typing import Protocol
from uuid import UUID

from app.domain.task import Task
from app.domain.task_list import TaskList
from app.domain.user import User


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
