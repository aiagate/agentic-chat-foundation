"""Add durable AgentRun workflow state.

Revision ID: 202607101600
Revises: 202606281200
Create Date: 2026-07-10 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202607101600"
down_revision: str | Sequence[str] | None = "202606281200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation_coordinators",
        sa.Column("conversation_key", sa.String(length=512), nullable=False),
        sa.Column("active_run_id", sa.String(length=26), nullable=True),
        sa.Column("version", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("conversation_key"),
    )
    op.create_index(
        op.f("ix_conversation_coordinators_active_run_id"),
        "conversation_coordinators",
        ["active_run_id"],
        unique=False,
    )
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("conversation_key", sa.String(length=512), nullable=False),
        sa.Column("source_chat_id", sa.String(length=26), nullable=False),
        sa.Column("character_id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("chat_type", sa.String(length=20), nullable=False),
        sa.Column("guild_id", sa.String(length=255), nullable=False),
        sa.Column("channel_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("turn_number", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_turns", sa.Integer(), server_default="8", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_token", sa.String(length=36), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("wake_sequence", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["conversation_key"],
            ["conversation_coordinators.conversation_key"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["source_chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_chat_id"),
    )
    for column in (
        "conversation_key",
        "source_chat_id",
        "character_id",
        "user_id",
        "status",
        "next_attempt_at",
        "lease_token",
        "lease_expires_at",
    ):
        op.create_index(
            op.f(f"ix_agent_runs_{column}"), "agent_runs", [column], unique=False
        )
    op.create_table(
        "agent_tool_calls",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("agent_run_id", sa.String(length=26), nullable=False),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.String(length=100), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("envelope", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("continuation", sa.String(length=20), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("rendered_result", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("lease_token", sa.String(length=36), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["agent_run_id"], ["agent_runs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "agent_run_id",
        "turn_number",
        "status",
        "lease_token",
        "lease_expires_at",
    ):
        op.create_index(
            op.f(f"ix_agent_tool_calls_{column}"),
            "agent_tool_calls",
            [column],
            unique=False,
        )


def downgrade() -> None:
    for column in (
        "lease_expires_at",
        "lease_token",
        "status",
        "turn_number",
        "agent_run_id",
    ):
        op.drop_index(
            op.f(f"ix_agent_tool_calls_{column}"), table_name="agent_tool_calls"
        )
    op.drop_table("agent_tool_calls")
    for column in (
        "lease_expires_at",
        "lease_token",
        "next_attempt_at",
        "status",
        "user_id",
        "character_id",
        "source_chat_id",
        "conversation_key",
    ):
        op.drop_index(op.f(f"ix_agent_runs_{column}"), table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index(
        op.f("ix_conversation_coordinators_active_run_id"),
        table_name="conversation_coordinators",
    )
    op.drop_table("conversation_coordinators")
