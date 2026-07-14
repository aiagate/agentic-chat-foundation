"""Gemini service implementation."""

import json
import logging
import os
from typing import Any, cast

from flow_res import Err, Ok, Result
from google import genai
from google.genai import types
from pydantic import ValidationError

from app.contracts.messages.chat_history import ChatHistoryItem
from app.contracts.messages.generated_content import GeneratedContent
from app.contracts.messages.llm_request_context import render_agent_prompt
from app.contracts.messages.tool_contracts import (
    ToolCall,
    ToolDefinition,
)
from app.contracts.messages.tool_result_context import ToolResultContext
from app.contracts.ports.ai_service import (
    AIServiceError,
    IAIService,
)
from app.infrastructure.serializers.provider_tool_binding import (
    ProviderToolBinding,
    bind_provider_tools,
    canonical_tool_name,
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
    """Parse structured Gemini output into the DTO."""
    if isinstance(payload, str):
        try:
            loaded_payload = json.loads(payload)
        except ValueError:
            normalized = payload.strip()
            return GeneratedContent(contents=[normalized] if normalized else [])
        return _parse_generated_content(loaded_payload)
    try:
        return GeneratedContent.model_validate(payload)
    except ValidationError:
        return GeneratedContent(
            contents=[json.dumps(payload, ensure_ascii=False)],
        )


def _gemini_tools(bindings: list[ProviderToolBinding]) -> list[types.Tool]:
    """Translate canonical tools into Gemini function declarations."""

    if not bindings:
        return []
    declarations = [
        types.FunctionDeclaration(
            name=binding.alias,
            description=(
                f"Canonical tool: {binding.definition.name}. "
                f"{binding.definition.description}"
            ),
            parameters_json_schema=binding.definition.arguments_schema,
        )
        for binding in bindings
    ]
    return [types.Tool(function_declarations=declarations)]


def _gemini_function_calls(
    response: Any,
    bindings: list[ProviderToolBinding],
) -> list[ToolCall]:
    """Normalize Gemini native function calls into canonical tool calls."""

    raw_calls = getattr(response, "function_calls", None)
    if not isinstance(raw_calls, list):
        return []
    tool_calls: list[ToolCall] = []
    for raw_call in raw_calls:
        provider_name = getattr(raw_call, "name", None)
        arguments = getattr(raw_call, "args", None)
        if not isinstance(provider_name, str) or not isinstance(arguments, dict):
            raise ValueError("Gemini returned an invalid function call")
        tool_name = canonical_tool_name(provider_name, bindings)
        if tool_name is None:
            raise ValueError(f"Gemini returned an unknown tool: {provider_name}")
        tool_calls.append(ToolCall(tool_name=tool_name, arguments=arguments))
    return tool_calls


class GeminiService(IAIService):
    """Implementation using Google Gemini."""

    def __init__(self) -> None:
        api_key = os.getenv("GEMINI_API_KEY")
        self._model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
        self._client = genai.Client(api_key=api_key) if api_key else None

    async def generate_content(
        self,
        prompt: str,
        history: list[ChatHistoryItem],
        system_instruction: str | None = None,
        tool_definitions: list[ToolDefinition] | None = None,
        tool_results: list[ToolResultContext] | None = None,
    ) -> Result[GeneratedContent, AIServiceError]:
        """Generate structured content with Gemini."""
        if self._client is None:
            return Err(AIServiceError("Gemini API key not configured."))
        client = self._client

        try:
            instructions = _compose_instructions(
                system_instruction=system_instruction,
            )
            bindings = bind_provider_tools(tool_definitions)
            provider_tools = _gemini_tools(bindings)
            current_prompt = render_agent_prompt(
                prompt=prompt,
                tool_results=tool_results or [],
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
                    "tool_results": [
                        result.model_dump(mode="json") for result in tool_results or []
                    ],
                    "contents": _serialize_gemini_contents(messages, current_prompt),
                    "tool_definitions": serialize_tool_definitions(tool_definitions),
                },
            )
            config = types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(
                    thinking_level=types.ThinkingLevel.LOW,
                ),
                max_output_tokens=2048,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True
                ),
            )
            if provider_tools:
                config.tools = provider_tools
            else:
                config.response_mime_type = "application/json"
            config.system_instruction = instructions

            response = await call_with_exponential_backoff(
                lambda: client.aio.models.generate_content(
                    model=self._model,
                    contents=cast(
                        list[types.ContentOrDict],
                        messages
                        + [
                            types.Content(
                                role="user",
                                parts=[types.Part(text=current_prompt)],
                            )
                        ],
                    ),
                    config=config,
                ),
                service_name="Gemini",
                logger=logger,
            )
            native_tool_calls = _gemini_function_calls(response, bindings)
            if response.parsed is not None:
                parsed_content = _parse_generated_content(response.parsed)
                combined_tool_calls = [*parsed_content.tool_calls, *native_tool_calls]
                if parsed_content.contents or combined_tool_calls:
                    logger.info(
                        "Gemini response accepted: model=%s source=parsed contents=%s tool_calls=%s",
                        self._model,
                        len(parsed_content.contents),
                        len(combined_tool_calls),
                    )
                    return Ok(
                        GeneratedContent(
                            contents=parsed_content.contents,
                            tool_calls=combined_tool_calls,
                        )
                    )
                logger.warning(
                    "Gemini structured output was empty; trying raw text fallback."
                )
            if response.text is None:
                if native_tool_calls:
                    return Ok(GeneratedContent(tool_calls=native_tool_calls))
                return Err(AIServiceError("No content generated."))
            try:
                parsed_content = _parse_generated_content(response.text)
                combined_tool_calls = [*parsed_content.tool_calls, *native_tool_calls]
                if parsed_content.contents or combined_tool_calls:
                    logger.info(
                        "Gemini response accepted: model=%s source=text contents=%s tool_calls=%s",
                        self._model,
                        len(parsed_content.contents),
                        len(combined_tool_calls),
                    )
                    return Ok(
                        GeneratedContent(
                            contents=parsed_content.contents,
                            tool_calls=combined_tool_calls,
                        )
                    )
                return Err(AIServiceError("Gemini returned empty structured output."))
            except ValidationError as e:
                return Err(AIServiceError(f"Invalid Gemini structured output: {e}"))
        except Exception as e:
            return Err(
                AIServiceError(
                    f"Gemini API Error: {e}",
                    code="gemini_api_error",
                    retryable=not isinstance(e, (ValueError, ValidationError)),
                )
            )


def _compose_instructions(
    *,
    system_instruction: str | None,
) -> str:
    return system_instruction or "You are a helpful assistant."


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
                    for part in message.parts or []
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
