"""The `Task` domain entity (design ADR-02, tasks spec)."""

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID, uuid4

from app.domain.exceptions import InvalidStatusTransitionError
from app.domain.value_objects import (
    DESCRIPTION_MAX_LENGTH,
    TITLE_MAX_LENGTH,
    Priority,
    TaskStatus,
    can_transition,
    ensure_due_date_not_past,
    normalize_optional_text,
    normalize_required_text,
)


@dataclass(slots=True, kw_only=True)
class Task:
    """A unit of work inside a `TaskList`."""

    id: UUID
    list_id: UUID
    title: str
    description: str | None
    status: TaskStatus
    priority: Priority
    due_date: date | None
    assignee_id: UUID | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        list_id: UUID,
        title: str,
        description: str | None,
        priority: Priority,
        due_date: date | None,
        today: date,
        now: datetime,
    ) -> "Task":
        """Build a new `Task` with a fresh identity, `status = pending`, and
        normalized/validated fields."""
        ensure_due_date_not_past(due_date, today)
        return cls(
            id=uuid4(),
            list_id=list_id,
            title=normalize_required_text(
                title, field="title", max_len=TITLE_MAX_LENGTH
            ),
            description=normalize_optional_text(
                description, field="description", max_len=DESCRIPTION_MAX_LENGTH
            ),
            status=TaskStatus.PENDING,
            priority=priority,
            due_date=due_date,
            assignee_id=None,
            created_at=now,
            updated_at=now,
        )

    def change_status(self, new: TaskStatus, now: datetime) -> None:
        """Move to `new` if it is one of the four valid edges; otherwise
        raise `InvalidStatusTransitionError` (tasks spec: strict state
        machine, same-status included)."""
        if not can_transition(self.status, new):
            raise InvalidStatusTransitionError(self.status.value, new.value)
        self.status = new
        self.updated_at = now

    def rename(self, title: str, now: datetime) -> None:
        """Set a new `title`, normalized and validated the same way as
        `create`."""
        self.title = normalize_required_text(
            title, field="title", max_len=TITLE_MAX_LENGTH
        )
        self.updated_at = now

    def describe(self, description: str | None, now: datetime) -> None:
        """Set a new `description`; blank/`None` clears it."""
        self.description = normalize_optional_text(
            description, field="description", max_len=DESCRIPTION_MAX_LENGTH
        )
        self.updated_at = now

    def set_priority(self, priority: Priority, now: datetime) -> None:
        """Set a new `priority`."""
        self.priority = priority
        self.updated_at = now

    def reschedule(self, due_date: date | None, today: date, now: datetime) -> None:
        """Set a new `due_date`, validated against `today`; `None` clears
        it (tasks spec: due_date-in-past rule applied on every write)."""
        ensure_due_date_not_past(due_date, today)
        self.due_date = due_date
        self.updated_at = now

    def assign(self, user_id: UUID | None, now: datetime) -> None:
        """Set a new `assignee_id`; `None` unassigns."""
        self.assignee_id = user_id
        self.updated_at = now
