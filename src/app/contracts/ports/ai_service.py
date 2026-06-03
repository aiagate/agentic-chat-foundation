"""AI service port."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from flow_res import Result

from app.contracts.messages.chat_history import ChatHistoryItem
from app.contracts.messages.generated_content import GeneratedContent
from app.contracts.messages.tool_contracts import ToolDefinition


@dataclass
class AIServiceError(Exception):
    """Represents an error from an AI service."""

    message: str

    def __str__(self) -> str:
        return self.message


class IAIService(ABC):
    """Interface for AI content generation."""

    @abstractmethod
    async def generate_content(
        self,
        prompt: str,
        history: list[ChatHistoryItem],
        system_instruction: str | None = None,
        tool_definitions: list[ToolDefinition] | None = None,
    ) -> Result[GeneratedContent, AIServiceError]:
        """Generate structured content from prompt and history."""
        pass
