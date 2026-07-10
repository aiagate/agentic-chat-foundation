"""OpenAI GPT service implementation."""

import json
import logging
import os
from typing import Any, cast

from flow_res import Err, Ok, Result
from openai import AsyncOpenAI
from openai.types.responses import ResponseInputItemParam

from app.contracts.messages.chat_history import ChatHistoryItem
from app.contracts.messages.generated_content import GeneratedContent
from app.contracts.messages.tool_contracts import (
    ToolDefinition,
    render_tool_definitions,
)
from app.contracts.ports.ai_service import (
    AIServiceError,
    IAIService,
)
from app.infrastructure.services.ai_request_logging import (
    log_ai_request_context,
    serialize_history,
    serialize_tool_definitions,
)
from app.infrastructure.services.retry_support import (
    call_with_exponential_backoff,
)

logger = logging.getLogger(__name__)


def _parse_generated_content(payload: Any) -> GeneratedContent:
    """Parse structured OpenAI output into the DTO."""
    if isinstance(payload, str):
        return GeneratedContent.model_validate_json(payload)
    return GeneratedContent.model_validate(payload)


class GptService(IAIService):
    """Implementation using OpenAI Responses API."""

    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        self._client = AsyncOpenAI(api_key=api_key) if api_key else None

    async def generate_content(
        self,
        prompt: str,
        history: list[ChatHistoryItem],
        system_instruction: str | None = None,
        tool_definitions: list[ToolDefinition] | None = None,
    ) -> Result[GeneratedContent, AIServiceError]:
        """Generate structured content with OpenAI."""
        if self._client is None:
            return Err(AIServiceError("OpenAI API key not configured."))
        client = self._client

        try:
            instructions = _compose_instructions(
                system_instruction=system_instruction,
                tool_definitions=tool_definitions,
            )
            input_messages = _history_to_openai_input(history)
            input_messages.append({"role": "user", "content": prompt})
            log_ai_request_context(
                logger,
                service_name="OpenAI",
                payload={
                    "model": "gpt-4o-mini",
                    "instructions": instructions,
                    "history": serialize_history(history),
                    "prompt": prompt,
                    "input_messages": input_messages,
                    "tool_definitions": serialize_tool_definitions(tool_definitions),
                },
            )

            response = await call_with_exponential_backoff(
                lambda: client.responses.create(
                    model="gpt-4o-mini",
                    instructions=instructions,
                    input=cast(list[ResponseInputItemParam], input_messages),
                    store=False,
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": "generated_content",
                            "schema": GeneratedContent.model_json_schema(),
                            "strict": True,
                        }
                    },
                ),
                service_name="OpenAI",
                logger=logger,
            )
            return Ok(_parse_generated_content(json.loads(response.output_text)))
        except Exception as e:
            return Err(AIServiceError(f"OpenAI API Error: {e}"))


def _compose_instructions(
    *,
    system_instruction: str | None,
    tool_definitions: list[ToolDefinition] | None,
) -> str:
    instructions = system_instruction or "You are a helpful assistant."
    if tool_definitions:
        instructions = "\n\n".join(
            [
                instructions,
                render_tool_definitions(tool_definitions),
            ]
        )
    return instructions


def _history_to_openai_input(
    history: list[ChatHistoryItem],
) -> list[dict[str, str]]:
    input_messages: list[dict[str, str]] = []
    for item in history:
        input_messages.append(
            {
                "role": item.role,
                "content": item.content,
            }
        )
    return input_messages
