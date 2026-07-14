"""Simplify conversation storage and remove retired workflow tables.

The application no longer persists durable agent runs, outbox messages, or
organization-management data.  Conversation rows are kept, but their old
channel-specific TPH columns are replaced with one channel-neutral shape.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202607141200"
down_revision: str | Sequence[str] | None = "202607101600"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _drop_table_if_present(table_name: str) -> None:
    """Drop a retired table when upgrading databases from any supported head."""

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name in inspector.get_table_names():
        op.drop_table(table_name)


def upgrade() -> None:
    """Migrate legacy chat rows and remove retired persistence concerns."""

    # Drop dependent workflow tables before changing chats.  Their data is
    # intentionally discarded because durable recovery is outside the product
    # scope; the raw conversation log remains the source of truth.
    for table_name in (
        "agent_tool_calls",
        "agent_runs",
        "conversation_coordinators",
        "outbox_messages",
        "memory_index_document_backups",
        "team_memberships",
        "teams",
        "users",
    ):
        _drop_table_if_present(table_name)

    # Add the replacement columns as nullable first so existing records can be
    # copied before the old columns are removed and constraints tightened.
    existing_indexes = {
        str(index["name"])
        for index in sa.inspect(op.get_bind()).get_indexes("chats")
        if index.get("name")
    }
    with op.batch_alter_table("chats", schema=None) as batch_op:
        batch_op.add_column(sa.Column("channel", sa.String(length=20), nullable=True))
        batch_op.add_column(
            sa.Column(
                "external_conversation_id", sa.String(length=255), nullable=True
            )
        )
        batch_op.add_column(
            sa.Column(
                "external_participant_id", sa.String(length=255), nullable=True
            )
        )
        batch_op.add_column(
            sa.Column("external_message_id", sa.String(length=255), nullable=True)
        )
        batch_op.add_column(
            sa.Column("channel_metadata", sa.JSON(), nullable=True)
        )

    # Legacy records did not have an external message id.  Keep it NULL so a
    # later webhook id can be recorded without fabricating provider identifiers.
    # Unknown identifiers are retained under a stable sentinel rather than
    # deleting old history that predates the new channel contract.
    op.execute(
        sa.text(
            """
            UPDATE chats
            SET channel = lower(type),
                external_conversation_id = COALESCE(
                    discord_channel_id,
                    line_group_id,
                    line_room_id,
                    line_user_id,
                    user_id,
                    'unknown'
                ),
                external_participant_id = COALESCE(
                    user_id,
                    line_user_id,
                    'unknown'
                ),
                channel_metadata = '{}'
            """
        )
    )

    # SQLite uses batch recreation for ALTER TABLE operations; PostgreSQL can
    # execute the same operation directly.  Keep the old role nullable during
    # the migration and normalize historical rows to user messages.
    op.execute(sa.text("UPDATE chats SET role = COALESCE(role, 'user')"))
    with op.batch_alter_table("chats", schema=None) as batch_op:
        for index_name in (
            "ix_chats_type",
            "ix_chats_user_id",
            "ix_chats_role",
        ):
            if index_name in existing_indexes:
                batch_op.drop_index(index_name)
        batch_op.alter_column(
            "channel",
            existing_type=sa.String(length=20),
            nullable=False,
        )
        batch_op.alter_column(
            "external_conversation_id",
            existing_type=sa.String(length=255),
            nullable=False,
        )
        batch_op.alter_column(
            "external_participant_id",
            existing_type=sa.String(length=255),
            nullable=False,
        )
        batch_op.alter_column(
            "channel_metadata",
            existing_type=sa.JSON(),
            nullable=False,
        )
        batch_op.alter_column(
            "role",
            existing_type=sa.String(length=32),
            nullable=False,
        )
        for column_name in (
            "type",
            "user_id",
            "version",
            "discord_guild_id",
            "discord_channel_id",
            "line_user_id",
            "line_group_id",
            "line_room_id",
        ):
            batch_op.drop_column(column_name)
        batch_op.create_index("ix_chats_external_conversation_id", ["external_conversation_id"])
        batch_op.create_index("ix_chats_external_participant_id", ["external_participant_id"])
        batch_op.create_index("ix_chats_external_message_id", ["external_message_id"])
        batch_op.create_unique_constraint(
            "uq_chats_channel_external_message_id",
            ["channel", "external_message_id"],
        )


def downgrade() -> None:
    """Restore only the old chat columns; retired data cannot be recovered."""

    existing_indexes = {
        str(index["name"])
        for index in sa.inspect(op.get_bind()).get_indexes("chats")
        if index.get("name")
    }
    with op.batch_alter_table("chats", schema=None) as batch_op:
        batch_op.drop_constraint(
            "uq_chats_channel_external_message_id", type_="unique"
        )
        for index_name in (
            "ix_chats_external_message_id",
            "ix_chats_external_participant_id",
            "ix_chats_external_conversation_id",
        ):
            if index_name in existing_indexes:
                batch_op.drop_index(index_name)
        batch_op.add_column(sa.Column("type", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("user_id", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("version", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("discord_guild_id", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("discord_channel_id", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("line_user_id", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("line_group_id", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("line_room_id", sa.String(length=255), nullable=True))
        batch_op.drop_column("channel")
        batch_op.drop_column("external_conversation_id")
        batch_op.drop_column("external_participant_id")
        batch_op.drop_column("external_message_id")
        batch_op.drop_column("channel_metadata")
        batch_op.alter_column("role", existing_type=sa.String(length=32), nullable=True)
