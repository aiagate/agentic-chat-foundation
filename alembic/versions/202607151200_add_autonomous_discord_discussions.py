"""Add local public discussion logs and private agent turns.

Revision ID: 202607151200
Revises: 202607141700
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202607151200"
down_revision: str | Sequence[str] | None = "202607141700"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create source-of-truth tables for one independent Discord bot."""

    op.create_table(
        "discussion_messages",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("external_message_id", sa.String(length=255), nullable=False),
        sa.Column("guild_id", sa.String(length=255), nullable=False),
        sa.Column("channel_id", sa.String(length=255), nullable=False),
        sa.Column("author_external_id", sa.String(length=255), nullable=False),
        sa.Column("author_display_name", sa.String(length=255), nullable=False),
        sa.Column("author_kind", sa.String(length=20), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("mentioned_self", sa.Boolean(), nullable=False),
        sa.Column("recovered", sa.Boolean(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "external_message_id",
            name="uq_discussion_messages_external_message_id",
        ),
    )
    op.create_index(
        "ix_discussion_messages_channel_id",
        "discussion_messages",
        ["channel_id"],
    )
    op.create_index(
        "ix_discussion_messages_occurred_at",
        "discussion_messages",
        ["occurred_at"],
    )

    op.create_table(
        "agent_turns",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("trigger_message_id", sa.String(length=26), nullable=False),
        sa.Column("channel_id", sa.String(length=255), nullable=False),
        sa.Column("character_id", sa.String(length=255), nullable=False),
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
            ["trigger_message_id"],
            ["discussion_messages.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "trigger_message_id",
            name="uq_agent_turns_trigger_message_id",
        ),
    )
    op.create_index("ix_agent_turns_channel_id", "agent_turns", ["channel_id"])
    op.create_index("ix_agent_turns_character_id", "agent_turns", ["character_id"])
    op.create_index("ix_agent_turns_disposition", "agent_turns", ["disposition"])
    op.create_index("ix_agent_turns_created_at", "agent_turns", ["created_at"])


def downgrade() -> None:
    """Drop local autonomous discussion state."""

    op.drop_index("ix_agent_turns_created_at", table_name="agent_turns")
    op.drop_index("ix_agent_turns_disposition", table_name="agent_turns")
    op.drop_index("ix_agent_turns_character_id", table_name="agent_turns")
    op.drop_index("ix_agent_turns_channel_id", table_name="agent_turns")
    op.drop_table("agent_turns")
    op.drop_index(
        "ix_discussion_messages_occurred_at", table_name="discussion_messages"
    )
    op.drop_index("ix_discussion_messages_channel_id", table_name="discussion_messages")
    op.drop_table("discussion_messages")
