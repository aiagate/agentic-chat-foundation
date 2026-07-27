"""Mock AI service implementation."""

import json
import logging

from flow_res import Ok, Result

from app.contracts.messages.ai_continuation import AIContinuation
from app.contracts.messages.chat_history import ChatHistoryItem
from app.contracts.messages.generated_content import GeneratedContent
from app.contracts.messages.tool_contracts import ToolDefinition
from app.contracts.messages.tool_result_context import ToolResultContext
from app.contracts.ports.ai_service import (
    AIServiceError,
    IAIService,
)
from app.infrastructure.services.ai_request_logging import (
    log_ai_request_context,
    serialize_history,
    serialize_tool_definitions,
)

logger = logging.getLogger(__name__)


class MockAIService(IAIService):
    """Deterministic AI service for local development and tests."""

    async def generate_content(
        self,
        prompt: str,
        history: list[ChatHistoryItem],
        system_instruction: str | None = None,
        tool_definitions: list[ToolDefinition] | None = None,
        tool_results: list[ToolResultContext] | None = None,
        continuation: AIContinuation | None = None,
    ) -> Result[GeneratedContent, AIServiceError]:
        """Return a simple structured mock response."""
        log_ai_request_context(
            logger,
            service_name="MockAI",
            payload={
                "history": serialize_history(history),
                "system_instruction": system_instruction,
                "prompt": prompt,
                "tool_results": [
                    result.model_dump(mode="json") for result in tool_results or []
                ],
                "tool_definitions": serialize_tool_definitions(tool_definitions),
                "continuation": continuation is not None,
            },
        )
        if system_instruction and '"speech_intent"' in system_instruction:
            return Ok(
                GeneratedContent(
                    contents=[
                        json.dumps(
                            {
                                "speech_intent": "silent",
                                "texts": [],
                                "private_reflection": {
                                    "observation": "Mock discussion observation",
                                    "stance": "neutral",
                                    "emotion": "calm",
                                    "next_intent": "wait for another message",
                                    "open_question": None,
                                },
                            }
                        )
                    ]
                )
            )
        if (
            system_instruction
            and "Classify only the user's relationship signal" in system_instruction
        ):
            return Ok(
                GeneratedContent(
                    contents=[
                        json.dumps(
                            {
                                "kind": "neutral",
                                "confidence": 1.0,
                                "reason": "mock neutral signal",
                                "source_chat_ids": [],
                            }
                        )
                    ]
                )
            )
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
