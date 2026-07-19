"""Value object for the channel-scoped conversation identity."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ConversationScope:
    """Identify one conversation history partition."""

    user_id: str
    character_id: str
    channel: str
    external_conversation_id: str

    def __post_init__(self) -> None:
        user_id = self.user_id.strip()
        character_id = self.character_id.strip()
        channel = self.channel.strip().lower()
        external_conversation_id = self.external_conversation_id.strip()
        if not user_id:
            raise ValueError("Conversation user_id cannot be empty")
        if not character_id:
            raise ValueError("Conversation character_id cannot be empty")
        if channel not in {"discord", "line"}:
            raise ValueError(f"Unsupported conversation channel: {self.channel}")
        if not external_conversation_id:
            raise ValueError("Conversation external_conversation_id cannot be empty")
        object.__setattr__(self, "user_id", user_id)
        object.__setattr__(self, "character_id", character_id)
        object.__setattr__(self, "channel", channel)
        object.__setattr__(
            self,
            "external_conversation_id",
            external_conversation_id,
        )
