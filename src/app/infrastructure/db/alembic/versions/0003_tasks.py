"""tasks

Revision ID: 0003_tasks
Revises: 0002_task_lists
Create Date: 2026-10-08

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_tasks"
down_revision: Union[str, None] = "0002_task_lists"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("list_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("assignee_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        # `MetaData`'s naming convention (`db/base.py`) renders CHECK names
        # as `ck_%(table_name)s_%(constraint_name)s`, substituting whatever
        # `name=` is given here as the `constraint_name` token -- even when
        # a name is already explicit (unlike unique/FK/index constraints,
        # where an explicit name bypasses the convention). Passing the bare
        # token (not a pre-built `ck_tasks_...` name) avoids a doubled
        # `ck_tasks_ck_tasks_...` constraint name; `db/models.py`'s
        # `sa.Enum(..., name="status"/"priority")` already relies on the
        # same bare-token convention.
        sa.CheckConstraint("length(btrim(title)) > 0", name="title_not_blank"),
        # Mirrors `db/models.py`'s `sa.Enum(..., native_enum=False,
        # create_constraint=True, ...)` by hand (design ADR-08): VARCHAR +
        # CHECK storing the enum *value*, not the native PG enum type.
        sa.CheckConstraint(
            "status IN ('pending', 'in_progress', 'done')", name="status"
        ),
        sa.CheckConstraint("priority IN ('low', 'medium', 'high')", name="priority"),
        sa.ForeignKeyConstraint(
            ["list_id"],
            ["task_lists.id"],
            name="fk_tasks_list_id_task_lists",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["assignee_id"],
            ["users.id"],
            name="fk_tasks_assignee_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tasks"),
    )
    op.create_index(
        "ix_tasks_list_id_created_at", "tasks", ["list_id", "created_at"], unique=False
    )
    op.create_index(
        op.f("ix_tasks_assignee_id"), "tasks", ["assignee_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_tasks_assignee_id"), table_name="tasks")
    op.drop_index("ix_tasks_list_id_created_at", table_name="tasks")
    op.drop_table("tasks")
