"""Add durable internally initiated Discord topic evaluations.

Revision ID: 202607151300
Revises: 202607151200
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202607151300"
down_revision: str | Sequence[str] | None = "202607151200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the local autonomous topic turn source-of-truth table."""

    op.create_table(
        "autonomous_topic_turns",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("guild_id", sa.String(length=255), nullable=False),
        sa.Column("channel_id", sa.String(length=255), nullable=False),
        sa.Column("character_id", sa.String(length=255), nullable=False),
        sa.Column("baseline_message_id", sa.String(length=26), nullable=True),
        sa.Column("disposition", sa.String(length=20), nullable=False),
        sa.Column("private_reflection", sa.JSON(), nullable=True),
        sa.Column("proposed_texts", sa.JSON(), nullable=False),
        sa.Column("published_external_message_ids", sa.JSON(), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["baseline_message_id"],
            ["discussion_messages.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_autonomous_topic_turns_guild_id",
        "autonomous_topic_turns",
        ["guild_id"],
    )
    op.create_index(
        "ix_autonomous_topic_turns_channel_id",
        "autonomous_topic_turns",
        ["channel_id"],
    )
    op.create_index(
        "ix_autonomous_topic_turns_character_id",
        "autonomous_topic_turns",
        ["character_id"],
    )
    op.create_index(
        "ix_autonomous_topic_turns_disposition",
        "autonomous_topic_turns",
        ["disposition"],
    )
    op.create_index(
        "ix_autonomous_topic_turns_created_at",
        "autonomous_topic_turns",
        ["created_at"],
    )


def downgrade() -> None:
    """Remove durable autonomous topic evaluations."""

    op.drop_index(
        "ix_autonomous_topic_turns_created_at",
        table_name="autonomous_topic_turns",
    )
    op.drop_index(
        "ix_autonomous_topic_turns_disposition",
        table_name="autonomous_topic_turns",
    )
    op.drop_index(
        "ix_autonomous_topic_turns_character_id",
        table_name="autonomous_topic_turns",
    )
    op.drop_index(
        "ix_autonomous_topic_turns_channel_id",
        table_name="autonomous_topic_turns",
    )
    op.drop_index(
        "ix_autonomous_topic_turns_guild_id",
        table_name="autonomous_topic_turns",
    )
    op.drop_table("autonomous_topic_turns")
