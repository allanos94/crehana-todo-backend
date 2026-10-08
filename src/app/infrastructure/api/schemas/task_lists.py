"""Task-list request/response schemas, reusing the domain's
`NAME_MAX_LENGTH`/`DESCRIPTION_MAX_LENGTH` limits (design ADR-13)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.value_objects import DESCRIPTION_MAX_LENGTH, NAME_MAX_LENGTH


class CreateTaskListRequest(BaseModel):
    """`name` is required; blank-after-trim is rejected by the domain, not
    here, so the error contract stays consistent across create and update."""

    name: str = Field(max_length=NAME_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)


class UpdateTaskListRequest(BaseModel):
    """Both fields are optional; the router uses `model_dump(exclude_unset=True)`
    so an omitted field stays `UNSET` while an explicit `null` reaches the
    use case as `None` (design ADR-04)."""

    name: str | None = Field(default=None, max_length=NAME_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)


class TaskListResponse(BaseModel):
    """A task list's public shape."""

    id: UUID
    owner_id: UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
