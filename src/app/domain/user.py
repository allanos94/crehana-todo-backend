"""The `User` domain entity (design ADR-02)."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4


@dataclass(slots=True, kw_only=True)
class User:
    """A registered account. Identified by `id`, created with a hashed password."""

    id: UUID
    email: str
    hashed_password: str
    created_at: datetime

    @classmethod
    def create(cls, *, email: str, hashed_password: str, now: datetime) -> "User":
        """Build a new `User` with a fresh identity and a normalized email."""
        return cls(
            id=uuid4(),
            email=email.strip().lower(),
            hashed_password=hashed_password,
            created_at=now,
        )
