"""The `User` response schema, shared by registration and `/users/me`."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class UserResponse(BaseModel):
    """A registered user's public identity. Never carries the password hash."""

    id: UUID
    email: str
    created_at: datetime
