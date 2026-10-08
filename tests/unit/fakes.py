"""In-memory fakes for unit-testing the application layer without a real DB
or I/O (design ADR-14). Extended by later slices with task-list/task
repositories, a password hasher fake, and a recording notifier.
"""

from __future__ import annotations

import copy
from datetime import date, datetime
from typing import Self
from uuid import UUID

from app.application.exceptions import InvalidTokenError
from app.application.ports import TokenPair, TokenType
from app.domain.user import User


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


class FakeUnitOfWork:
    """Fake `UnitOfWork`: a `committed` flag, and rollback restores a snapshot
    of the repositories taken when the transaction opened."""

    def __init__(self, users: InMemoryUserRepository | None = None) -> None:
        self.users = users if users is not None else InMemoryUserRepository()
        self.committed = False
        self._snapshot: InMemoryUserRepository | None = None

    async def __aenter__(self) -> Self:
        self.committed = False
        self._snapshot = copy.deepcopy(self.users)
        return self

    async def __aexit__(self, *exc: object) -> None:
        if not self.committed and self._snapshot is not None:
            self.users = self._snapshot
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
