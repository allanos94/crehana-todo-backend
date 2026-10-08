"""Application ports as `typing.Protocol`s (design ADR-05).

Repository Protocols live in `domain/repositories.py`. This module starts
with `Clock` and `UnitOfWork`; `PasswordHasher` and `TokenService` are added
by slice 1b. `NotificationService` is added by slice 5.
"""

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol, Self
from uuid import UUID

from app.domain.repositories import UserRepository


class Clock(Protocol):
    """A source of the current time, injected so use cases stay deterministic."""

    def now(self) -> datetime:  # tz-aware, UTC
        ...

    def today(self) -> date:  # now().date() in UTC
        ...


class PasswordHasher(Protocol):
    """Hashes and verifies passwords. Async because Argon2 is deliberately
    CPU-heavy (~50ms) and the adapter offloads it with `asyncio.to_thread`."""

    #: A fixed hash with no matching plaintext, so `LoginUser` can run a real
    #: `verify()` call against an unknown email without ever hashing a value
    #: that was never submitted — equalizing timing with a wrong password.
    dummy_hash: str

    async def hash(self, raw: str) -> str: ...

    async def verify(self, raw: str, hashed: str) -> bool: ...


class TokenType(StrEnum):
    """The `type` claim carried by every issued JWT (design ADR-11)."""

    ACCESS = "access"
    REFRESH = "refresh"


@dataclass(frozen=True, slots=True)
class TokenPair:
    """An issued access/refresh token pair, ready to serialize in a response."""

    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int


class TokenService(Protocol):
    """Issues and decodes HS256 JWT access/refresh token pairs."""

    def issue_pair(self, user_id: UUID) -> TokenPair: ...

    def decode(
        self, token: str, expected_type: TokenType
    ) -> UUID: ...  # raises InvalidTokenError


class UnitOfWork(Protocol):
    """Owns one transaction, one `AsyncSession`, and the repositories on it."""

    users: UserRepository

    async def __aenter__(self) -> Self: ...

    async def __aexit__(self, *exc: object) -> None: ...  # rolls back if not committed

    async def commit(
        self,
    ) -> None: ...  # may raise ConflictError (constraint translation)
