"""The `User` response schema, shared by registration and `/users/me`."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.infrastructure.api.schemas.tasks import TaskResponse


class UserResponse(BaseModel):
    """A registered user's public identity. Never carries the password hash."""

    id: UUID
    email: str
    created_at: datetime


class AssignedTaskPageResponse(BaseModel):
    """A page of the caller's own assigned tasks, across every list
    (task-assignment spec: `GET /users/me/tasks`). No `completion_percentage`
    here -- that is a per-list metric, not meaningful across lists."""

    items: list[TaskResponse]
    total: int
