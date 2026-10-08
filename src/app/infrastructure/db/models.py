"""SQLAlchemy ORM models (design ADR-08).

`TaskModel` lands in a later slice (3b). No ORM `relationship()`s are
declared — the flat domain does not need them; cascades are
database-level.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class UserModel(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class TaskListModel(Base):
    __tablename__ = "task_lists"
    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="ck_task_lists_name_not_blank"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


# A functional unique index cannot be expressed inside `__table_args__`
# (the class body has no `TaskListModel` name to reference yet), so it is
# declared standalone, mirroring migration `0002_task_lists`'s
# `op.create_index(..., sa.text("lower(name)"), ...)` exactly (design
# ADR-08/ADR-10): per-owner, case-insensitive name uniqueness.
Index(
    "uq_task_lists_owner_id_lower_name",
    TaskListModel.owner_id,
    func.lower(TaskListModel.name),
    unique=True,
)
