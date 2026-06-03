"""Gemini service implementation."""

import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any, cast

from flow_res import Err, Ok, Result
from google import genai
from google.genai import types
from pydantic import ValidationError

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

logger = logging.getLogger(__name__)
_MAX_ATTEMPTS = 4


def _parse_generated_content(payload: Any) -> GeneratedContent:
    """Parse structured Gemini output into the DTO."""
    if isinstance(payload, str):
        return GeneratedContent.model_validate_json(payload)
    return GeneratedContent.model_validate(payload)


class GeminiService(IAIService):
    """Implementation using Google Gemini."""

    def __init__(self) -> None:
        api_key = os.getenv("GEMINI_API_KEY")
        self._model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self._client = genai.Client(api_key=api_key) if api_key else None

    async def generate_content(
        self,
        prompt: str,
        history: list[ChatHistoryItem],
        system_instruction: str | None = None,
        tool_definitions: list[ToolDefinition] | None = None,
    ) -> Result[GeneratedContent, AIServiceError]:
        """Generate structured content with Gemini."""
        if self._client is None:
            return Err(AIServiceError("Gemini API key not configured."))
        client = self._client

        try:
            instructions = _compose_instructions(
                system_instruction=system_instruction,
                tool_definitions=tool_definitions,
            )
            messages, system_texts = _history_to_gemini_contents(history)
            if system_texts:
                instructions = "\n\n".join([instructions, *system_texts])
            config = types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0),
                max_output_tokens=2048,
                response_mime_type="application/json",
                response_json_schema=GeneratedContent.model_json_schema(),
            )
            config.system_instruction = instructions

            response = await _generate_with_retries(
                lambda: client.aio.models.generate_content(
                    model=self._model,
                    contents=cast(
                        list[types.ContentOrDict],
                        messages
                        + [
                            types.Content(
                                role="user",
                                parts=[types.Part(text=prompt)],
                            )
                        ],
                    ),
                    config=config,
                ),
                service_name="Gemini",
            )
            if response.parsed is not None:
                return Ok(_parse_generated_content(response.parsed))
            if response.text is None:
                return Err(AIServiceError("No content generated."))
            try:
                return Ok(_parse_generated_content(response.text))
            except ValidationError as e:
                return Err(AIServiceError(f"Invalid Gemini structured output: {e}"))
        except Exception as e:
            return Err(AIServiceError(f"Gemini API Error: {e}"))


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


def _history_to_gemini_contents(
    history: list[ChatHistoryItem],
) -> tuple[list[types.Content], list[str]]:
    contents: list[types.Content] = []
    system_texts: list[str] = []
    for item in history:
        if item.role == "system":
            if item.content.strip():
                system_texts.append(item.content.strip())
            continue
        role = "user" if item.role == "user" else "model"
        contents.append(
            types.Content(
                role=role,
                parts=[types.Part(text=item.content)],
            )
        )
    return contents, system_texts


async def _generate_with_retries[T](
    operation: Callable[[], Awaitable[T]],
    *,
    service_name: str,
) -> T:
    """Run an external AI call with up to three retries."""

    last_error: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return await operation()
        except Exception as error:
            last_error = error
            if attempt >= _MAX_ATTEMPTS:
                raise
            logger.warning(
                "%s API call failed; retrying %s/%s: %s",
                service_name,
                attempt,
                _MAX_ATTEMPTS - 1,
                error,
            )

    assert last_error is not None
    raise last_error
