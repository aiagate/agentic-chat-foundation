"""Add character-scoped chats and relationship state.

Revision ID: 202607151500
Revises: 202607151400
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202607151500"
down_revision: str | Sequence[str] | None = "202607151400"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create character relationship persistence and scope existing chats."""

    with op.batch_alter_table("chats") as batch_op:
        batch_op.add_column(
            sa.Column(
                "character_id",
                sa.String(length=100),
                nullable=False,
                server_default="shirasagi-reina",
            )
        )
        batch_op.create_index("ix_chats_character_id", ["character_id"])

    op.create_table(
        "character_relationships",
        sa.Column("character_id", sa.String(length=100), nullable=False),
        sa.Column("user_id", sa.String(length=26), nullable=False),
        sa.Column("affection", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "affection >= 0 AND affection <= 100",
            name="ck_character_relationships_affection",
        ),
        sa.CheckConstraint("version >= 1", name="ck_character_relationships_version"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("character_id", "user_id"),
    )
    op.create_table(
        "relationship_signal_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("character_id", sa.String(length=100), nullable=False),
        sa.Column("user_id", sa.String(length=26), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("proposed_delta", sa.Integer(), nullable=False),
        sa.Column("applied_delta", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reason", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('provisional', 'confirmed', 'superseded')",
            name="ck_relationship_signal_events_status",
        ),
        sa.CheckConstraint(
            "kind IN ('strong_negative', 'negative', 'neutral', 'positive', 'strong_positive')",
            name="ck_relationship_signal_events_kind",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_relationship_signal_events_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["character_id", "user_id"],
            ["character_relationships.character_id", "character_relationships.user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_relationship_signal_events_character_id",
        "relationship_signal_events",
        ["character_id"],
    )
    op.create_index(
        "ix_relationship_signal_events_user_id",
        "relationship_signal_events",
        ["user_id"],
    )
    op.create_index(
        "ix_relationship_signal_events_status",
        "relationship_signal_events",
        ["status"],
    )
    op.create_index(
        "ix_relationship_signal_events_observed_at",
        "relationship_signal_events",
        ["observed_at"],
    )
    op.create_table(
        "relationship_signal_sources",
        sa.Column("signal_id", sa.String(length=64), nullable=False),
        sa.Column("chat_id", sa.String(length=26), nullable=False),
        sa.ForeignKeyConstraint(
            ["signal_id"], ["relationship_signal_events.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("signal_id", "chat_id"),
        sa.UniqueConstraint(
            "signal_id", "chat_id", name="uq_relationship_signal_sources"
        ),
    )
    op.create_index(
        "ix_relationship_signal_sources_chat_id",
        "relationship_signal_sources",
        ["chat_id"],
    )


def downgrade() -> None:
    """Remove relationship persistence and character chat scoping."""

    op.drop_index(
        "ix_relationship_signal_sources_chat_id",
        table_name="relationship_signal_sources",
    )
    op.drop_table("relationship_signal_sources")
    op.drop_index(
        "ix_relationship_signal_events_observed_at",
        table_name="relationship_signal_events",
    )
    op.drop_index(
        "ix_relationship_signal_events_status",
        table_name="relationship_signal_events",
    )
    op.drop_index(
        "ix_relationship_signal_events_user_id",
        table_name="relationship_signal_events",
    )
    op.drop_index(
        "ix_relationship_signal_events_character_id",
        table_name="relationship_signal_events",
    )
    op.drop_table("relationship_signal_events")
    op.drop_table("character_relationships")
    with op.batch_alter_table("chats") as batch_op:
        batch_op.drop_index("ix_chats_character_id")
        batch_op.drop_column("character_id")
