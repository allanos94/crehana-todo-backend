"""Application ports as `typing.Protocol`s (design ADR-05).

Repository Protocols live in `domain/repositories.py`. This module starts
with `Clock` and `UnitOfWork`; `PasswordHasher`, `TokenService`, and
`NotificationService` are added by later slices (1b, 5).
"""

from datetime import date, datetime
from typing import Protocol, Self

from app.domain.repositories import UserRepository


class Clock(Protocol):
    """A source of the current time, injected so use cases stay deterministic."""

    def now(self) -> datetime:  # tz-aware, UTC
        ...

    def today(self) -> date:  # now().date() in UTC
        ...


class UnitOfWork(Protocol):
    """Owns one transaction, one `AsyncSession`, and the repositories on it."""

    users: UserRepository

    async def __aenter__(self) -> Self: ...

    async def __aexit__(self, *exc: object) -> None: ...  # rolls back if not committed

    async def commit(
        self,
    ) -> None: ...  # may raise ConflictError (constraint translation)
