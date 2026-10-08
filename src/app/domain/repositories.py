"""Repository Protocols (design ADR-05).

Repositories are `typing.Protocol`s so fakes satisfy them structurally,
without inheritance. `TaskRepository` lands in a later slice (3a); this
module now also carries `TaskListRepository` (slice 2a).
"""

from typing import Protocol
from uuid import UUID

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
