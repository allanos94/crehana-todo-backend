"""Repository Protocols (design ADR-05).

Repositories are `typing.Protocol`s so fakes satisfy them structurally,
without inheritance. `TaskListRepository` and `TaskRepository` land in
later slices (2a/3a); this module starts with `UserRepository` only.
"""

from typing import Protocol
from uuid import UUID

from app.domain.user import User


class UserRepository(Protocol):
    async def add(self, user: User) -> None: ...

    async def get_by_id(self, user_id: UUID) -> User | None: ...

    async def get_by_email(self, email: str) -> User | None: ...
