"""Add memory-consolidated chat source projection.

Revision ID: 202606221200
Revises: 202606121200
Create Date: 2026-06-22 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202606221200"
down_revision: str | Sequence[str] | None = "202606121200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the processed-source projection."""

    op.create_table(
        "memory_consolidated_chat_sources",
        sa.Column("chat_id", sa.String(length=26), nullable=False),
        sa.Column("consolidated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("chat_id"),
    )
    op.create_index(
        op.f("ix_memory_consolidated_chat_sources_consolidated_at"),
        "memory_consolidated_chat_sources",
        ["consolidated_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the processed-source projection."""

    op.drop_index(
        op.f("ix_memory_consolidated_chat_sources_consolidated_at"),
        table_name="memory_consolidated_chat_sources",
    )
    op.drop_table("memory_consolidated_chat_sources")
