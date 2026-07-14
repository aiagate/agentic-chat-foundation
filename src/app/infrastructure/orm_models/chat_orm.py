"""Persistence model for channel-neutral conversation messages."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, DateTime, String, UniqueConstraint, func
from sqlmodel import Field, SQLModel


class ChatORM(SQLModel, table=True):
    """A row in the raw conversation log.

    Incoming and outgoing messages share the same shape.  Channel adapters keep
    their provider-specific identifiers in ``channel_metadata`` instead of
    adding nullable columns or ORM subclasses for every provider.
    """

    __tablename__ = "chats"  # type: ignore[reportAssignmentType]

    id: str | None = Field(default=None, primary_key=True, max_length=26)
    channel: str = Field(sa_column=Column(String(20), nullable=False, index=True))
    external_conversation_id: str = Field(
        max_length=255,
        sa_column=Column(String(255), nullable=False, index=True),
    )
    external_participant_id: str = Field(
        max_length=255,
        sa_column=Column(String(255), nullable=False, index=True),
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

    def __init__(self, **data: Any) -> None:
        """Accept the former constructor names while callers migrate.

        The compatibility translation is intentionally kept outside the table
        schema: old names are not mapped columns and therefore cannot reappear
        in new migrations.
        """
        legacy_type = data.pop("type", None)
        legacy_user_id = data.pop("user_id", None)
        legacy_channel_id = data.pop("discord_channel_id", None)
        legacy_guild_id = data.pop("discord_guild_id", None)
        legacy_line_user_id = data.pop("line_user_id", None)
        legacy_group_id = data.pop("line_group_id", None)
        legacy_room_id = data.pop("line_room_id", None)
        data.pop("version", None)
        if "channel" not in data and legacy_type is not None:
            data["channel"] = str(legacy_type).lower()
        if "external_participant_id" not in data:
            participant = legacy_user_id or legacy_line_user_id
            if participant is not None:
                data["external_participant_id"] = str(participant)
        if "external_conversation_id" not in data:
            conversation = (
                legacy_channel_id
                or legacy_group_id
                or legacy_room_id
                or legacy_line_user_id
                or legacy_user_id
            )
            if conversation is not None:
                data["external_conversation_id"] = str(conversation)
        if "channel_metadata" not in data:
            metadata: dict[str, Any] = {}
            if legacy_guild_id is not None:
                metadata["guild_id"] = str(legacy_guild_id)
            if legacy_channel_id is not None:
                metadata["channel_id"] = str(legacy_channel_id)
            data["channel_metadata"] = metadata
        data.setdefault("role", "user")
        super().__init__(**data)

    @property
    def type(self) -> str:
        """Legacy discriminator view for old read-only adapters."""
        return self.channel.upper()

    @property
    def user_id(self) -> str:
        """Legacy participant view."""
        return self.external_participant_id

    @property
    def discord_channel_id(self) -> str | None:
        return self.channel_metadata.get("channel_id")

    @property
    def discord_guild_id(self) -> str | None:
        return self.channel_metadata.get("guild_id")

    @property
    def line_user_id(self) -> str | None:
        return self.external_participant_id

    @property
    def line_group_id(self) -> str | None:
        return self.channel_metadata.get("group_id")

    @property
    def line_room_id(self) -> str | None:
        return self.channel_metadata.get("room_id")
