"""Add memory index documents table.

Revision ID: 202605301900
Revises: 250d95a50640
Create Date: 2026-05-30 19:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202605301900"
down_revision: str | Sequence[str] | None = "250d95a50640"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "memory_index_documents",
        sa.Column("source_path", sa.String(length=512), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=True),
        sa.Column("memory_type", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("indexed_text", sa.Text(), nullable=False),
        sa.Column("tags_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("timeline_type", sa.String(length=50), nullable=True),
        sa.Column("occurred_at", sa.String(length=64), nullable=True),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
        sa.Column("importance", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("decay_score", sa.Float(), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("source_path"),
    )
    op.create_index(
        op.f("ix_memory_index_documents_content_hash"),
        "memory_index_documents",
        ["content_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_memory_index_documents_memory_type"),
        "memory_index_documents",
        ["memory_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_memory_index_documents_occurred_at"),
        "memory_index_documents",
        ["occurred_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_memory_index_documents_source_id"),
        "memory_index_documents",
        ["source_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_memory_index_documents_status"),
        "memory_index_documents",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_memory_index_documents_timeline_type"),
        "memory_index_documents",
        ["timeline_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_memory_index_documents_updated_at"),
        "memory_index_documents",
        ["updated_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_memory_index_documents_user_id"),
        "memory_index_documents",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_memory_index_documents_user_id"),
        table_name="memory_index_documents",
    )
    op.drop_index(
        op.f("ix_memory_index_documents_updated_at"),
        table_name="memory_index_documents",
    )
    op.drop_index(
        op.f("ix_memory_index_documents_timeline_type"),
        table_name="memory_index_documents",
    )
    op.drop_index(
        op.f("ix_memory_index_documents_status"),
        table_name="memory_index_documents",
    )
    op.drop_index(
        op.f("ix_memory_index_documents_source_id"),
        table_name="memory_index_documents",
    )
    op.drop_index(
        op.f("ix_memory_index_documents_occurred_at"),
        table_name="memory_index_documents",
    )
    op.drop_index(
        op.f("ix_memory_index_documents_memory_type"),
        table_name="memory_index_documents",
    )
    op.drop_index(
        op.f("ix_memory_index_documents_content_hash"),
        table_name="memory_index_documents",
    )
    op.drop_table("memory_index_documents")
