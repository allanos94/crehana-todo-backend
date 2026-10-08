"""Commands and results for the auth use cases (design ADR-04)."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RegisterUserCommand:
    email: str
    password: str


@dataclass(frozen=True, slots=True)
class RegisterUserResult:
    id: UUID
    email: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class LoginUserCommand:
    email: str
    password: str


@dataclass(frozen=True, slots=True)
class RefreshTokensCommand:
    refresh_token: str


@dataclass(frozen=True, slots=True)
class GetCurrentUserCommand:
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class CurrentUserResult:
    id: UUID
    email: str
    created_at: datetime
