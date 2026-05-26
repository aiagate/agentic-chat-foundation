"""AI service port."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from flow_res import Result

from app.contracts.messages.generated_content import GeneratedContent
from app.domain.aggregates.chat import Chat


@dataclass(frozen=True)
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
        history: list[Chat],
        system_instruction: str | None = None,
    ) -> Result[GeneratedContent, AIServiceError]:
        """Generate structured content from prompt and history."""
        pass
