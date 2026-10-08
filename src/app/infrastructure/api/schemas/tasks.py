"""Task request/response schemas, reusing the domain's `TITLE_MAX_LENGTH`/
`DESCRIPTION_MAX_LENGTH` limits (design ADR-13).

`priority` defaults to `Priority.MEDIUM` when omitted on create: neither
the spec nor the design names a default, so this slice fills that gap with
the conventional task-tracker default (recorded in `DECISION_LOG.md`).
"""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.value_objects import (
    DESCRIPTION_MAX_LENGTH,
    TITLE_MAX_LENGTH,
    Priority,
    TaskStatus,
)


class CreateTaskRequest(BaseModel):
    """`title` is required; blank-after-trim is rejected by the domain,
    not here, so the error contract stays consistent across create and
    update."""

    title: str = Field(max_length=TITLE_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    priority: Priority = Priority.MEDIUM
    due_date: date | None = None


class UpdateTaskRequest(BaseModel):
    """Every field is optional; the router uses
    `model_dump(exclude_unset=True)` so an omitted field stays `UNSET`
    while an explicit `null` reaches the use case as `None` (design
    ADR-04). `due_date` is re-validated only when the client actually
    patches it."""

    title: str | None = Field(default=None, max_length=TITLE_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    priority: Priority | None = None
    due_date: date | None = None


class ChangeTaskStatusRequest(BaseModel):
    """The target status for `PATCH .../status` (tasks spec: strict state
    machine)."""

    status: TaskStatus


class TaskResponse(BaseModel):
    """A task's public shape."""

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


class TaskPageResponse(BaseModel):
    """A filtered, paginated page of tasks (tasks spec: `items`/`total`
    reflect the applied filters and pagination; `completion_percentage`
    never does -- design ADR-10)."""

    items: list[TaskResponse]
    total: int
    completion_percentage: float
