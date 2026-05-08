"""add user_settings table

Revision ID: 001
Revises:
Create Date: 2026-05-08
"""

from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_settings",
        sa.Column("user_id", sa.String, primary_key=True),
        sa.Column("timezone", sa.String, nullable=False, server_default="Europe/Amsterdam"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        ),
    )


def downgrade() -> None:
    op.drop_table("user_settings")
