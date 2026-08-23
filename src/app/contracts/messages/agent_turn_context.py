"""Read model required to execute one agent turn."""

from pydantic import BaseModel, ConfigDict

from app.contracts.messages.chat_history import ChatHistoryItem
from app.contracts.messages.conversation_context import ConversationContext


class AgentTurnContext(BaseModel):
    """Resolved prompt and conversation state for one agent turn."""

    model_config = ConfigDict(extra="forbid")

    prompt: str
    recent_history: list[ChatHistoryItem]
    conversation: ConversationContext
