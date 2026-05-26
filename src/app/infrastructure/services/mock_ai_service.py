"""Mock AI service implementation."""

from flow_res import Ok, Result

from app.contracts.messages.generated_content import GeneratedContent
from app.contracts.ports.ai_service import (
    AIServiceError,
    IAIService,
)
from app.domain.aggregates.chat import Chat


class MockAIService(IAIService):
    """Deterministic AI service for local development and tests."""

    async def generate_content(
        self,
        prompt: str,
        history: list[Chat],
        system_instruction: str | None = None,
    ) -> Result[GeneratedContent, AIServiceError]:
        """Return a simple structured mock response."""
        _ = history
        _ = system_instruction
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
