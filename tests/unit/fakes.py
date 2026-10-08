"""In-memory fakes for unit-testing the application layer without a real DB
or I/O (design ADR-14). Extended by later slices with task repositories, a
password hasher fake, and a recording notifier.
"""

from __future__ import annotations

import copy
from datetime import date, datetime
from typing import Self
from uuid import UUID

from app.application.exceptions import InvalidTokenError
from app.application.ports import TokenPair, TokenType
from app.domain.repositories import TaskCounts, TaskFilter
from app.domain.task import Task
from app.domain.task_list import TaskList
from app.domain.user import User
from app.domain.value_objects import TaskStatus


class InMemoryUserRepository:
    """A plain in-memory store. Uniqueness is the use case's job, not the repo's."""

    def __init__(self) -> None:
        self._by_id: dict[UUID, User] = {}

    async def add(self, user: User) -> None:
        self._by_id[user.id] = user

    async def get_by_id(self, user_id: UUID) -> User | None:
        return self._by_id.get(user_id)

    async def get_by_email(self, email: str) -> User | None:
        return next(
            (user for user in self._by_id.values() if user.email == email), None
        )


class InMemoryTaskListRepository:
    """A plain in-memory store enforcing case-insensitive per-owner
    uniqueness through `name_exists`, mirroring the real functional unique
    index (`uq_task_lists_owner_id_lower_name`, shipped in slice 2b)."""

    def __init__(self) -> None:
        self._by_id: dict[UUID, TaskList] = {}

    async def add(self, task_list: TaskList) -> None:
        self._by_id[task_list.id] = task_list

    async def update(self, task_list: TaskList) -> None:
        self._by_id[task_list.id] = task_list

    async def get(self, list_id: UUID) -> TaskList | None:
        return self._by_id.get(list_id)

    async def list_by_owner(self, owner_id: UUID) -> list[TaskList]:
        return [
            task_list
            for task_list in self._by_id.values()
            if task_list.owner_id == owner_id
        ]

    async def name_exists(
        self, owner_id: UUID, name: str, exclude_id: UUID | None = None
    ) -> bool:
        lowered = name.lower()
        return any(
            task_list.owner_id == owner_id
            and task_list.name.lower() == lowered
            and task_list.id != exclude_id
            for task_list in self._by_id.values()
        )

    async def delete(self, list_id: UUID) -> None:
        self._by_id.pop(list_id, None)


class InMemoryTaskRepository:
    """A plain in-memory store for `Task` (CRUD plus filtered, paginated
    `search`; `list_by_assignee` lands in slice 5)."""

    def __init__(self) -> None:
        self._by_id: dict[UUID, Task] = {}

    async def add(self, task: Task) -> None:
        self._by_id[task.id] = task

    async def update(self, task: Task) -> None:
        self._by_id[task.id] = task

    async def get(self, task_id: UUID) -> Task | None:
        return self._by_id.get(task_id)

    async def delete(self, task_id: UUID) -> None:
        self._by_id.pop(task_id, None)

    async def search(
        self, list_id: UUID, filters: TaskFilter, limit: int, offset: int
    ) -> tuple[list[Task], TaskCounts]:
        """Mirror the SQL semantics of design ADR-10: counts are computed
        over every task in the list regardless of `filters`, while `items`
        (ordered by `created_at`, `id`, then paginated) and the filtered
        total both respect `filters`."""
        all_in_list = [task for task in self._by_id.values() if task.list_id == list_id]
        total_all = len(all_in_list)
        done_all = sum(1 for task in all_in_list if task.status == TaskStatus.DONE)
        matching = [
            task
            for task in all_in_list
            if (filters.status is None or task.status == filters.status)
            and (filters.priority is None or task.priority == filters.priority)
        ]
        matching.sort(key=lambda task: (task.created_at, task.id))
        total_filtered = len(matching)
        page = matching[offset : offset + limit]
        counts = TaskCounts(
            total_all=total_all, done_all=done_all, total_filtered=total_filtered
        )
        return page, counts


class FakeUnitOfWork:
    """Fake `UnitOfWork`: a `committed` flag, and rollback restores a snapshot
    of the repositories taken when the transaction opened."""

    def __init__(
        self,
        users: InMemoryUserRepository | None = None,
        task_lists: InMemoryTaskListRepository | None = None,
        tasks: InMemoryTaskRepository | None = None,
    ) -> None:
        self.users = users if users is not None else InMemoryUserRepository()
        self.task_lists = (
            task_lists if task_lists is not None else InMemoryTaskListRepository()
        )
        self.tasks = tasks if tasks is not None else InMemoryTaskRepository()
        self.committed = False
        self._snapshot: (
            tuple[
                InMemoryUserRepository,
                InMemoryTaskListRepository,
                InMemoryTaskRepository,
            ]
            | None
        ) = None

    async def __aenter__(self) -> Self:
        self.committed = False
        self._snapshot = (
            copy.deepcopy(self.users),
            copy.deepcopy(self.task_lists),
            copy.deepcopy(self.tasks),
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if not self.committed and self._snapshot is not None:
            self.users, self.task_lists, self.tasks = self._snapshot
        self._snapshot = None

    async def commit(self) -> None:
        self.committed = True


class FakePasswordHasher:
    """A `PasswordHasher` double with no real crypto: `"hashed:" + raw`."""

    dummy_hash = "hashed:__dummy__"

    async def hash(self, raw: str) -> str:
        return f"hashed:{raw}"

    async def verify(self, raw: str, hashed: str) -> bool:
        return hashed == f"hashed:{raw}"


class FakeTokenService:
    """A deterministic `TokenService` double: tokens are `"{type}:{user_id}"`."""

    def __init__(self) -> None:
        self.issued_for: list[UUID] = []

    def issue_pair(self, user_id: UUID) -> TokenPair:
        self.issued_for.append(user_id)
        return TokenPair(
            access_token=f"access:{user_id}",
            refresh_token=f"refresh:{user_id}",
            token_type="bearer",
            expires_in=900,
        )

    def decode(self, token: str, expected_type: TokenType) -> UUID:
        prefix, separator, raw_id = token.partition(":")
        if not separator or prefix != expected_type.value:
            raise InvalidTokenError()
        return UUID(raw_id)


class FixedClock:
    """A `Clock` double with a fixed `now`/`today`, for deterministic tests."""

    def __init__(self, now: datetime, today: date | None = None) -> None:
        self._now = now
        self._today = today if today is not None else now.date()

    def now(self) -> datetime:
        return self._now

    def today(self) -> date:
        return self._today
