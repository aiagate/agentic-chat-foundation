"""Remove obsolete agent profile rows from the memory index projection.

Revision ID: 202607151400
Revises: 202607151300
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202607151400"
down_revision: str | Sequence[str] | None = "202607151300"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Delete derived rows for agent profile configuration files."""

    op.execute(
        sa.text(
            "DELETE FROM memory_index_documents "
            "WHERE user_id IS NULL OR source_path LIKE 'profiles/agent/%'"
        )
    )
    with op.batch_alter_table("memory_index_documents") as batch_op:
        batch_op.alter_column(
            "user_id",
            existing_type=sa.String(length=255),
            nullable=False,
        )


def downgrade() -> None:
    """Restore nullable scope without reconstructing derived agent rows."""

    with op.batch_alter_table("memory_index_documents") as batch_op:
        batch_op.alter_column(
            "user_id",
            existing_type=sa.String(length=255),
            nullable=True,
        )
