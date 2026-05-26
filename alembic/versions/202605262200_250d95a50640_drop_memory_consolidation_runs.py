"""drop memory consolidation runs

Revision ID: 250d95a50640
Revises: 8c1f2a4b9d30
Create Date: 2026-05-26 22:00:51.621471

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "250d95a50640"
down_revision: str | Sequence[str] | None = "8c1f2a4b9d30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_table("memory_consolidation_runs")


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table(
        "memory_consolidation_runs",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("run_key", sa.String(length=255), nullable=False),
        sa.Column("job_name", sa.String(length=100), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_key"),
    )
    with op.batch_alter_table("memory_consolidation_runs", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_memory_consolidation_runs_job_name"),
            ["job_name"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_memory_consolidation_runs_status"),
            ["status"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_memory_consolidation_runs_target_date"),
            ["target_date"],
            unique=False,
        )
