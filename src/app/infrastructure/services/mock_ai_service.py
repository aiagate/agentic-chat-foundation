"""Mock AI service implementation."""

from flow_res import Ok, Result

from app.contracts.messages.chat_history import ChatHistoryItem
from app.contracts.messages.generated_content import GeneratedContent
from app.contracts.messages.tool_contracts import ToolDefinition
from app.contracts.ports.ai_service import (
    AIServiceError,
    IAIService,
)


class MockAIService(IAIService):
    """Deterministic AI service for local development and tests."""

    async def generate_content(
        self,
        prompt: str,
        history: list[ChatHistoryItem],
        system_instruction: str | None = None,
        tool_definitions: list[ToolDefinition] | None = None,
    ) -> Result[GeneratedContent, AIServiceError]:
        """Return a simple structured mock response."""
        _ = history
        _ = system_instruction
        _ = tool_definitions
        return Ok(
            GeneratedContent(
                contents=[
                    f"mock response: {prompt}",
                    "additional content",
                    "more content",
                    "even more content",
                ]
            )
        )
