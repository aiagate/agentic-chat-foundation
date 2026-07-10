"""ORM models for durable agent workflow state."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlmodel import Field, SQLModel


class ConversationCoordinatorORM(SQLModel, table=True):
    """One serialization mailbox per logical conversation."""

    __tablename__ = "conversation_coordinators"  # type: ignore[reportAssignmentType]

    conversation_key: str = Field(primary_key=True, max_length=512)
    active_run_id: str | None = Field(default=None, max_length=26, index=True)
    version: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        ),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        ),
    )


class AgentRunORM(SQLModel, table=True):
    """Persisted state machine for one accepted user message."""

    __tablename__ = "agent_runs"  # type: ignore[reportAssignmentType]

    id: str = Field(primary_key=True, max_length=26)
    conversation_key: str = Field(
        sa_column=Column(
            String(512),
            ForeignKey(
                "conversation_coordinators.conversation_key", ondelete="CASCADE"
            ),
            nullable=False,
            index=True,
        )
    )
    source_chat_id: str = Field(
        sa_column=Column(
            String(26),
            ForeignKey("chats.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            index=True,
        )
    )
    character_id: str = Field(max_length=255, index=True)
    user_id: str = Field(max_length=255, index=True)
    chat_type: str = Field(max_length=20)
    guild_id: str = Field(max_length=255)
    channel_id: str = Field(max_length=255)
    status: str = Field(max_length=32, index=True)
    turn_number: int = Field(default=0)
    max_turns: int = Field(default=8)
    attempt_count: int = Field(default=0)
    next_attempt_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True, index=True),
    )
    lease_token: str | None = Field(default=None, max_length=36, index=True)
    lease_expires_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True, index=True),
    )
    wake_sequence: int = Field(default=0)
    last_error_code: str | None = Field(default=None, max_length=100)
    last_error_message: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    version: int = Field(default=0)
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        ),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        ),
    )
    completed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )


class AgentToolCallORM(SQLModel, table=True):
    """Persisted tool call and result owned by an AgentRun."""

    __tablename__ = "agent_tool_calls"  # type: ignore[reportAssignmentType]

    id: str = Field(primary_key=True, max_length=36)
    agent_run_id: str = Field(
        sa_column=Column(
            String(26),
            ForeignKey("agent_runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    turn_number: int = Field(index=True)
    tool_name: str = Field(max_length=100)
    arguments: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    envelope: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    status: str = Field(max_length=32, index=True)
    continuation: str = Field(max_length=20)
    result: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    rendered_result: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    error_code: str | None = Field(default=None, max_length=100)
    error_message: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    attempt_count: int = Field(default=0)
    lease_token: str | None = Field(default=None, max_length=36, index=True)
    lease_expires_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True, index=True),
    )
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        ),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        ),
    )
    completed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
