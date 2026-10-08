"""The `TaskList` domain entity (design ADR-02)."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from app.domain.value_objects import (
    DESCRIPTION_MAX_LENGTH,
    NAME_MAX_LENGTH,
    normalize_optional_text,
    normalize_required_text,
)


@dataclass(slots=True, kw_only=True)
class TaskList:
    """An owner-scoped collection of tasks."""

    id: UUID
    owner_id: UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        owner_id: UUID,
        name: str,
        description: str | None,
        now: datetime,
    ) -> "TaskList":
        """Build a new `TaskList` with a fresh identity and normalized fields."""
        return cls(
            id=uuid4(),
            owner_id=owner_id,
            name=normalize_required_text(name, field="name", max_len=NAME_MAX_LENGTH),
            description=normalize_optional_text(
                description, field="description", max_len=DESCRIPTION_MAX_LENGTH
            ),
            created_at=now,
            updated_at=now,
        )

    def rename(self, name: str, now: datetime) -> None:
        """Set a new `name`, normalized and validated the same way as `create`."""
        self.name = normalize_required_text(name, field="name", max_len=NAME_MAX_LENGTH)
        self.updated_at = now

    def describe(self, description: str | None, now: datetime) -> None:
        """Set a new `description`; blank/`None` clears it."""
        self.description = normalize_optional_text(
            description, field="description", max_len=DESCRIPTION_MAX_LENGTH
        )
        self.updated_at = now
