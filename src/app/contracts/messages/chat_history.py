"""Chat history DTOs shared across application layers."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.messages.chat_type import ChatType


class ChatHistoryItem(BaseModel):
    """One persisted chat message with its conversational role."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable chat identifier.")
    user_id: str | None = Field(
        default=None,
        description="Owning user identifier, if available.",
    )
    chat_type: ChatType = Field(description="Chat channel type.")
    role: Literal["user", "assistant", "system"] = Field(
        description="Conversation role for LLM input."
    )
    content: str = Field(description="Normalized message text.")
    occurred_at: datetime | None = Field(
        default=None,
        description="Observed timestamp.",
    )


class ChatHistoryWindow(BaseModel):
    """Recent unconsolidated chat history and its memory boundary."""

    model_config = ConfigDict(extra="forbid")

    items: list[ChatHistoryItem] = Field(default_factory=list)
    memory_boundary_at: datetime | None = None
