"""Gemini service implementation."""

import json
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
from app.infrastructure.services.ai_request_logging import (
    log_ai_request_context,
    serialize_history,
    serialize_tool_definitions,
)

logger = logging.getLogger(__name__)
_MAX_ATTEMPTS = 4


def _parse_generated_content(payload: Any) -> GeneratedContent:
    """Parse structured Gemini output into the DTO."""
    if isinstance(payload, str):
        try:
            loaded_payload = json.loads(payload)
        except ValueError:
            return GeneratedContent.model_validate_json(payload)
        return _parse_generated_content(loaded_payload)
    try:
        return GeneratedContent.model_validate(payload)
    except ValidationError:
        return GeneratedContent(
            contents=[json.dumps(payload, ensure_ascii=False)],
        )


class GeminiService(IAIService):
    """Implementation using Google Gemini."""

    def __init__(self) -> None:
        api_key = os.getenv("GEMINI_API_KEY")
        self._model = os.getenv("GEMINI_MODEL", "gemini-3.1-pro-preview")
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
            log_ai_request_context(
                logger,
                service_name="Gemini",
                payload={
                    "model": self._model,
                    "system_instruction": instructions,
                    "history": serialize_history(history),
                    "system_texts": system_texts,
                    "prompt": prompt,
                    "contents": _serialize_gemini_contents(messages, prompt),
                    "tool_definitions": serialize_tool_definitions(tool_definitions),
                },
            )
            config = types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(
                    thinking_level=types.ThinkingLevel.LOW,
                ),
                max_output_tokens=2048,
                response_mime_type="application/json",
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
                parsed_content = _parse_generated_content(response.parsed)
                if parsed_content.contents or parsed_content.tool_calls:
                    logger.info(
                        "Gemini response accepted: model=%s source=parsed contents=%s tool_calls=%s",
                        self._model,
                        len(parsed_content.contents),
                        len(parsed_content.tool_calls),
                    )
                    return Ok(parsed_content)
                logger.warning(
                    "Gemini structured output was empty; trying raw text fallback."
                )
            if response.text is None:
                return Err(AIServiceError("No content generated."))
            try:
                parsed_content = _parse_generated_content(response.text)
                if parsed_content.contents or parsed_content.tool_calls:
                    logger.info(
                        "Gemini response accepted: model=%s source=text contents=%s tool_calls=%s",
                        self._model,
                        len(parsed_content.contents),
                        len(parsed_content.tool_calls),
                    )
                    return Ok(parsed_content)
                return Err(AIServiceError("Gemini returned empty structured output."))
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


def _serialize_gemini_contents(
    messages: list[types.Content],
    prompt: str,
) -> list[dict[str, object]]:
    """Convert Gemini contents into JSON-serializable dictionaries."""

    serialized_messages: list[dict[str, object]] = []
    for message in messages:
        serialized_messages.append(
            {
                "role": message.role,
                "parts": [
                    {
                        "text": part.text,
                    }
                    for part in message.parts
                ],
            }
        )
    serialized_messages.append(
        {
            "role": "user",
            "parts": [{"text": prompt}],
        }
    )
    return serialized_messages


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
