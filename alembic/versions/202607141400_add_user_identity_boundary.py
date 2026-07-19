"""Add canonical user identity boundary.

Revision ID: 202607141400
Revises: 202607141200
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202607141400"
down_revision: str | Sequence[str] | None = "202607141200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create explicit users and provider identity mappings."""

    op.create_table(
        "users",
        sa.Column("id", sa.String(length=26), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "user_channel_identities",
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("external_participant_id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=26), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.CheckConstraint(
            "channel IN ('discord', 'line')",
            name="ck_user_channel_identities_channel",
        ),
        sa.CheckConstraint(
            "length(trim(external_participant_id)) > 0",
            name="ck_user_channel_identities_external_participant_id",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("channel", "external_participant_id"),
    )
    op.create_index(
        "ix_user_channel_identities_user_id",
        "user_channel_identities",
        ["user_id"],
    )

    inspector = sa.inspect(op.get_bind())
    indexes = {
        str(index["name"])
        for index in inspector.get_indexes("chats")
        if index.get("name")
    }
    with op.batch_alter_table("chats", schema=None) as batch_op:
        if "ix_chats_external_message_id" in indexes:
            batch_op.drop_index("ix_chats_external_message_id")
        if "ix_chats_channel" not in indexes:
            batch_op.create_index("ix_chats_channel", ["channel"])
        if "ix_chats_role" not in indexes:
            batch_op.create_index("ix_chats_role", ["role"])


def downgrade() -> None:
    """Remove the canonical identity tables and restore the old chat index."""

    inspector = sa.inspect(op.get_bind())
    indexes = {
        str(index["name"])
        for index in inspector.get_indexes("chats")
        if index.get("name")
    }
    with op.batch_alter_table("chats", schema=None) as batch_op:
        if "ix_chats_role" in indexes:
            batch_op.drop_index("ix_chats_role")
        if "ix_chats_channel" in indexes:
            batch_op.drop_index("ix_chats_channel")
        if "ix_chats_external_message_id" not in indexes:
            batch_op.create_index(
                "ix_chats_external_message_id", ["external_message_id"]
            )
    op.drop_index(
        "ix_user_channel_identities_user_id",
        table_name="user_channel_identities",
    )
    op.drop_table("user_channel_identities")
    op.drop_table("users")
