"""Persistence models for one bot's autonomous Discord discussions."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, String, Text, func
from sqlmodel import Field, SQLModel


class DiscussionMessageORM(SQLModel, table=True):
    """One public Discord message observed by this bot."""

    __tablename__ = "discussion_messages"  # type: ignore[reportAssignmentType]

    id: str = Field(primary_key=True, max_length=26)
    external_message_id: str = Field(
        sa_column=Column(String(255), nullable=False, unique=True, index=True)
    )
    guild_id: str = Field(sa_column=Column(String(255), nullable=False, index=True))
    channel_id: str = Field(sa_column=Column(String(255), nullable=False, index=True))
    author_external_id: str = Field(
        sa_column=Column(String(255), nullable=False, index=True)
    )
    author_display_name: str = Field(sa_column=Column(String(255), nullable=False))
    author_kind: str = Field(sa_column=Column(String(20), nullable=False, index=True))
    message_text: str = Field(sa_column=Column(Text, nullable=False))
    mentioned_self: bool = Field(
        default=False, sa_column=Column(Boolean, nullable=False, default=False)
    )
    recovered: bool = Field(
        default=False, sa_column=Column(Boolean, nullable=False, default=False)
    )
    occurred_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True)
    )
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )


class AgentTurnORM(SQLModel, table=True):
    """One private evaluation performed by this bot's character."""

    __tablename__ = "agent_turns"  # type: ignore[reportAssignmentType]

    id: str = Field(primary_key=True, max_length=26)
    trigger_message_id: str = Field(
        sa_column=Column(
            String(26),
            ForeignKey("discussion_messages.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            index=True,
        )
    )
    channel_id: str = Field(sa_column=Column(String(255), nullable=False, index=True))
    character_id: str = Field(sa_column=Column(String(255), nullable=False, index=True))
    disposition: str = Field(sa_column=Column(String(20), nullable=False, index=True))
    private_reflection: dict[str, object] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    proposed_texts: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False, default=list)
    )
    published_external_message_ids: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False, default=list)
    )
    failure_reason: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True), server_default=func.now(), index=True
        ),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
        ),
    )


class AutonomousTopicTurnORM(SQLModel, table=True):
    """One locally initiated topic evaluation performed by this character."""

    __tablename__ = "autonomous_topic_turns"  # type: ignore[reportAssignmentType]

    id: str = Field(primary_key=True, max_length=26)
    guild_id: str = Field(sa_column=Column(String(255), nullable=False, index=True))
    channel_id: str = Field(sa_column=Column(String(255), nullable=False, index=True))
    character_id: str = Field(sa_column=Column(String(255), nullable=False, index=True))
    baseline_message_id: str | None = Field(
        default=None,
        sa_column=Column(
            String(26),
            ForeignKey("discussion_messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    disposition: str = Field(sa_column=Column(String(20), nullable=False, index=True))
    private_reflection: dict[str, object] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    proposed_texts: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False, default=list)
    )
    published_external_message_ids: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False, default=list)
    )
    failure_reason: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True), server_default=func.now(), index=True
        ),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
        ),
    )
