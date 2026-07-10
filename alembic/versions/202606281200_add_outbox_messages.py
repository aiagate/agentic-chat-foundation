"""Add transactional outbox messages.

Revision ID: 202606281200
Revises: 202606221200
Create Date: 2026-06-28 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202606281200"
down_revision: str | Sequence[str] | None = "202606221200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the transactional outbox table."""
    op.create_table(
        "outbox_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("topic", sa.String(length=255), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_token", sa.String(length=36), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "topic",
        "created_at",
        "published_at",
        "next_attempt_at",
        "claimed_at",
        "claim_token",
    ):
        op.create_index(
            op.f(f"ix_outbox_messages_{column}"),
            "outbox_messages",
            [column],
            unique=False,
        )


def downgrade() -> None:
    """Drop the transactional outbox table."""
    for column in (
        "next_attempt_at",
        "claim_token",
        "claimed_at",
        "published_at",
        "created_at",
        "topic",
    ):
        op.drop_index(
            op.f(f"ix_outbox_messages_{column}"),
            table_name="outbox_messages",
        )
    op.drop_table("outbox_messages")
