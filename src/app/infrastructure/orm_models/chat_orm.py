"""Persistence model for channel-neutral conversation messages."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Sequence,
    String,
    UniqueConstraint,
    func,
)
from sqlmodel import Field, SQLModel


class ChatORM(SQLModel, table=True):
    """A row in the raw conversation log.

    Incoming and outgoing messages share the same shape.  Channel adapters keep
    their provider-specific identifiers in ``channel_metadata`` instead of
    adding nullable columns or ORM subclasses for every provider.
    """

    __tablename__ = "chats"  # type: ignore[reportAssignmentType]

    id: str | None = Field(default=None, primary_key=True, max_length=26)
    character_id: str = Field(
        default="shirasagi-reina",
        max_length=100,
        sa_column=Column(String(100), nullable=False, index=True),
    )
    channel: str = Field(sa_column=Column(String(20), nullable=False, index=True))
    external_conversation_id: str = Field(
        max_length=255,
        sa_column=Column(String(255), nullable=False, index=True),
    )
    external_participant_id: str = Field(
        max_length=255,
        sa_column=Column(String(255), nullable=False, index=True),
    )
    user_id: str = Field(
        max_length=26,
        sa_column=Column(
            String(26),
            ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
    )
    accepted_sequence: int = Field(
        sa_column=Column(
            BigInteger,
            Sequence("chat_acceptance_sequence"),
            nullable=False,
            index=True,
        ),
    )
    # Provider message id is present for inbound messages and NULL for replies.
    external_message_id: str | None = Field(
        default=None,
        max_length=255,
        sa_column=Column(String(255), nullable=True),
    )
    role: str = Field(
        max_length=32,
        sa_column=Column(String(32), nullable=False, index=True),
    )
    message_content: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    channel_metadata: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, default=dict),
    )
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )

    __table_args__ = (
        UniqueConstraint(
            "channel",
            "external_message_id",
            name="uq_chats_channel_external_message_id",
        ),
    )
