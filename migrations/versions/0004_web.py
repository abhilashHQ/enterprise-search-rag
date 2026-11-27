"""web app: conversation owner and title, app settings

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("user_id", sa.String(64), nullable=True))
    op.add_column("conversations", sa.Column("title", sa.String(120), nullable=True))
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.JSON, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_index("ix_conversations_user_id", "conversations")
    op.drop_column("conversations", "title")
    op.drop_column("conversations", "user_id")
