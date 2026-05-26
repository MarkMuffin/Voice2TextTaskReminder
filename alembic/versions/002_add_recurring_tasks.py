"""add recurring_tasks table and extend tasks

Revision ID: 002
Revises: 001
Create Date: 2026-05-18
"""

from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recurring_tasks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String, nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("raw_text", sa.String, nullable=True),
        sa.Column("source", sa.String, nullable=False, server_default="telegram"),
        sa.Column("timezone", sa.String, nullable=False, server_default="Europe/Amsterdam"),
        sa.Column("status", sa.String, nullable=False, server_default="active"),
        sa.Column("recurrence_type", sa.String, nullable=False),
        sa.Column("interval", sa.Integer, nullable=False, server_default="1"),
        sa.Column("time_of_day", sa.String, nullable=False),
        sa.Column("day_of_week", sa.Integer, nullable=True),
        sa.Column("day_of_month", sa.Integer, nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
    )
    op.create_index("ix_recurring_tasks_user_id", "recurring_tasks", ["user_id"])
    op.create_index("ix_recurring_tasks_next_run_at", "recurring_tasks", ["next_run_at"])
    op.create_index(
        "ix_recurring_tasks_user_status", "recurring_tasks", ["user_id", "status"]
    )
    op.create_index(
        "ix_recurring_tasks_next_run_status", "recurring_tasks", ["next_run_at", "status"]
    )

    with op.batch_alter_table("tasks") as batch_op:
        batch_op.add_column(
            sa.Column(
                "recurring_task_id",
                sa.Integer,
                sa.ForeignKey("recurring_tasks.id"),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_index("ix_tasks_recurring_task_id", ["recurring_task_id"])
        batch_op.create_index(
            "uq_tasks_recurring_scheduled",
            ["recurring_task_id", "scheduled_for"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_index("uq_tasks_recurring_scheduled")
        batch_op.drop_index("ix_tasks_recurring_task_id")
        batch_op.drop_column("scheduled_for")
        batch_op.drop_column("recurring_task_id")

    op.drop_index("ix_recurring_tasks_next_run_status", "recurring_tasks")
    op.drop_index("ix_recurring_tasks_user_status", "recurring_tasks")
    op.drop_index("ix_recurring_tasks_next_run_at", "recurring_tasks")
    op.drop_index("ix_recurring_tasks_user_id", "recurring_tasks")
    op.drop_table("recurring_tasks")
