"""Add memory index backup snapshot table.

Revision ID: 202606121200
Revises: 3f5d8c24b6a1
Create Date: 2026-06-12 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202606121200"
down_revision: str | Sequence[str] | None = "3f5d8c24b6a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "memory_index_document_backups",
        sa.Column("scope_user_id", sa.String(length=255), nullable=False),
        sa.Column("source_path", sa.String(length=512), nullable=False),
        sa.Column("backed_up_at", sa.String(length=64), nullable=False),
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
        sa.PrimaryKeyConstraint("scope_user_id", "source_path"),
    )
    op.create_index(
        op.f("ix_memory_index_document_backups_backed_up_at"),
        "memory_index_document_backups",
        ["backed_up_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_memory_index_document_backups_content_hash"),
        "memory_index_document_backups",
        ["content_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_memory_index_document_backups_memory_type"),
        "memory_index_document_backups",
        ["memory_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_memory_index_document_backups_occurred_at"),
        "memory_index_document_backups",
        ["occurred_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_memory_index_document_backups_source_id"),
        "memory_index_document_backups",
        ["source_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_memory_index_document_backups_scope_user_id"),
        "memory_index_document_backups",
        ["scope_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_memory_index_document_backups_status"),
        "memory_index_document_backups",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_memory_index_document_backups_timeline_type"),
        "memory_index_document_backups",
        ["timeline_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_memory_index_document_backups_updated_at"),
        "memory_index_document_backups",
        ["updated_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_memory_index_document_backups_user_id"),
        "memory_index_document_backups",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_memory_index_document_backups_user_id"),
        table_name="memory_index_document_backups",
    )
    op.drop_index(
        op.f("ix_memory_index_document_backups_updated_at"),
        table_name="memory_index_document_backups",
    )
    op.drop_index(
        op.f("ix_memory_index_document_backups_timeline_type"),
        table_name="memory_index_document_backups",
    )
    op.drop_index(
        op.f("ix_memory_index_document_backups_status"),
        table_name="memory_index_document_backups",
    )
    op.drop_index(
        op.f("ix_memory_index_document_backups_scope_user_id"),
        table_name="memory_index_document_backups",
    )
    op.drop_index(
        op.f("ix_memory_index_document_backups_source_id"),
        table_name="memory_index_document_backups",
    )
    op.drop_index(
        op.f("ix_memory_index_document_backups_occurred_at"),
        table_name="memory_index_document_backups",
    )
    op.drop_index(
        op.f("ix_memory_index_document_backups_memory_type"),
        table_name="memory_index_document_backups",
    )
    op.drop_index(
        op.f("ix_memory_index_document_backups_content_hash"),
        table_name="memory_index_document_backups",
    )
    op.drop_index(
        op.f("ix_memory_index_document_backups_backed_up_at"),
        table_name="memory_index_document_backups",
    )
    op.drop_table("memory_index_document_backups")
