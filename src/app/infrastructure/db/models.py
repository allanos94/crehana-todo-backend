"""SQLAlchemy ORM models (design ADR-08).

No ORM `relationship()`s are declared — the flat domain does not need
them; cascades are database-level.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.value_objects import Priority, TaskStatus
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


class TaskModel(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        # Bare `name=` token (renders to `ck_tasks_title_not_blank` through
        # the naming convention) -- see `versions/0003_tasks.py` for why.
        CheckConstraint("length(btrim(title)) > 0", name="title_not_blank"),
        Index("ix_tasks_list_id_created_at", "list_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    list_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("task_lists.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # `native_enum=False` + `values_callable` (design ADR-08): stored as
    # VARCHAR + CHECK, with the DB holding the enum *value* (e.g.
    # "in_progress"), not the Python member name.
    status: Mapped[TaskStatus] = mapped_column(
        Enum(
            TaskStatus,
            native_enum=False,
            create_constraint=True,
            length=20,
            name="status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    priority: Mapped[Priority] = mapped_column(
        Enum(
            Priority,
            native_enum=False,
            create_constraint=True,
            length=20,
            name="priority",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    due_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
