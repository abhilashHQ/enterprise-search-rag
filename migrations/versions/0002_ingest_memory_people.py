"""outbox, memories, people, sources

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

NOW = sa.func.now()


def upgrade() -> None:
    op.create_table(
        "outbox",
        sa.Column("id", sa.Integer, sa.Identity(), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("doc_id", sa.String(512), nullable=False),
        sa.Column("payload", sa.JSON, server_default=sa.text("'{}'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_outbox_published_at", "outbox", ["published_at"])
    op.create_table(
        "memories",
        sa.Column("id", sa.Integer, sa.Identity(), primary_key=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("proposed_by", sa.String(64)),
        sa.Column("conversation_id", sa.String(32)),
        sa.Column("decided_by", sa.String(64)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
    )
    op.create_index("ix_memories_status", "memories", ["status"])
    op.create_table(
        "people",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("email", sa.String(256), unique=True),
        sa.Column("aliases", sa.JSON, server_default=sa.text("'[]'"), nullable=False),
        sa.Column("role", sa.String(128)),
        sa.Column("team", sa.String(128)),
        sa.Column("topics", sa.JSON, server_default=sa.text("'[]'"), nullable=False),
        sa.Column("sources", sa.JSON, server_default=sa.text("'{}'"), nullable=False),
        sa.Column("doc_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("search_text", sa.Text, server_default="", nullable=False),
        sa.Column("is_admin", sa.Boolean, server_default=sa.text("false"), nullable=False),
    )
    op.create_table(
        "sources",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("config", sa.JSON, server_default=sa.text("'{}'"), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "source_files",
        sa.Column("source_id", sa.String(64), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rel_path", sa.String(1024), nullable=False),
        sa.Column("doc_id", sa.String(512), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("source_id", "rel_path"),
    )


def downgrade() -> None:
    for t in ("source_files", "sources", "people", "memories", "outbox"):
        op.drop_table(t)
