"""OpenAI GPT service implementation."""

import json
import logging
import os
from typing import Any, cast

from flow_res import Err, Ok, Result
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from openai.types.responses import FunctionToolParam, ResponseInputItemParam

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

_DEFAULT_OPENAI_MODEL = "gpt-5.6-terra"
_DEFAULT_OPENAI_REASONING_EFFORT = "low"
_DEFAULT_OPENAI_TEXT_VERBOSITY = "low"
_DEFAULT_OPENAI_MAX_OUTPUT_TOKENS = 1024


def _parse_openai_response(
    response: Any,
    bindings: list[ProviderToolBinding],
) -> GeneratedContent:
    """Normalize OpenAI text and native function calls into the app DTO."""

    contents: list[str] = []
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        contents.append(output_text.strip())

    tool_calls: list[ToolCall] = []
    raw_output = getattr(response, "output", [])
    if isinstance(raw_output, list):
        for item in raw_output:
            if getattr(item, "type", None) != "function_call":
                continue
            provider_name = getattr(item, "name", None)
            raw_arguments = getattr(item, "arguments", None)
            if not isinstance(provider_name, str) or not isinstance(raw_arguments, str):
                raise ValueError("OpenAI returned an invalid function call")
            tool_name = canonical_tool_name(provider_name, bindings)
            if tool_name is None:
                raise ValueError(f"OpenAI returned an unknown tool: {provider_name}")
            arguments = json.loads(raw_arguments)
            if not isinstance(arguments, dict):
                raise ValueError("OpenAI tool arguments must be a JSON object")
            tool_calls.append(ToolCall(tool_name=tool_name, arguments=arguments))

    if not contents and not tool_calls:
        raise ValueError("OpenAI returned neither text nor tool calls")
    return GeneratedContent(contents=contents, tool_calls=tool_calls)


def _openai_tools(
    bindings: list[ProviderToolBinding],
) -> list[FunctionToolParam]:
    """Translate canonical tool definitions into Responses API functions."""

    return [
        FunctionToolParam(
            type="function",
            name=binding.alias,
            description=(
                f"Canonical tool: {binding.definition.name}. "
                f"{binding.definition.description}"
            ),
            parameters=binding.definition.arguments_schema,
            strict=False,
        )
        for binding in bindings
    ]


def _is_retryable_openai_error(error: Exception) -> bool:
    """Return whether an OpenAI failure can plausibly succeed on retry."""

    if isinstance(error, (APIConnectionError, APITimeoutError)):
        return True
    if isinstance(error, APIStatusError):
        return error.status_code in {408, 409, 429} or error.status_code >= 500
    if isinstance(error, (ValueError, json.JSONDecodeError)):
        return False
    return True


class GptService(IAIService):
    """Implementation using OpenAI Responses API."""

    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        self._client = AsyncOpenAI(api_key=api_key) if api_key else None
        self._model = os.getenv("OPENAI_MODEL", _DEFAULT_OPENAI_MODEL)
        self._reasoning_effort = os.getenv(
            "OPENAI_REASONING_EFFORT",
            _DEFAULT_OPENAI_REASONING_EFFORT,
        )
        self._text_verbosity = os.getenv(
            "OPENAI_TEXT_VERBOSITY",
            _DEFAULT_OPENAI_TEXT_VERBOSITY,
        )
        self._max_output_tokens = _positive_int_env(
            "OPENAI_MAX_OUTPUT_TOKENS",
            _DEFAULT_OPENAI_MAX_OUTPUT_TOKENS,
        )

    async def generate_content(
        self,
        prompt: str,
        history: list[ChatHistoryItem],
        system_instruction: str | None = None,
        tool_definitions: list[ToolDefinition] | None = None,
        tool_results: list[ToolResultContext] | None = None,
    ) -> Result[GeneratedContent, AIServiceError]:
        """Generate structured content with OpenAI."""
        if self._client is None:
            return Err(AIServiceError("OpenAI API key not configured."))
        client = self._client

        try:
            instructions = _compose_instructions(
                system_instruction=system_instruction,
            )
            bindings = bind_provider_tools(tool_definitions)
            provider_tools = _openai_tools(bindings)
            input_messages = _history_to_openai_input(history)
            current_prompt = render_agent_prompt(
                prompt=prompt,
                tool_results=tool_results or [],
            )
            input_messages.append({"role": "user", "content": current_prompt})
            log_ai_request_context(
                logger,
                service_name="OpenAI",
                payload={
                    "model": self._model,
                    "generation_params": {
                        "reasoning_effort": self._reasoning_effort,
                        "text_verbosity": self._text_verbosity,
                        "max_output_tokens": self._max_output_tokens,
                    },
                    "instructions": instructions,
                    "history": serialize_history(history),
                    "prompt": prompt,
                    "tool_results": [
                        result.model_dump(mode="json") for result in tool_results or []
                    ],
                    "input_messages": input_messages,
                    "tool_definitions": serialize_tool_definitions(tool_definitions),
                },
            )

            async def create_response() -> Any:
                request_input = cast(list[ResponseInputItemParam], input_messages)
                request_kwargs: dict[str, Any] = {
                    "model": self._model,
                    "instructions": instructions,
                    "input": request_input,
                    "store": False,
                    "max_output_tokens": self._max_output_tokens,
                    "reasoning": {"effort": self._reasoning_effort},
                    "text": {"verbosity": self._text_verbosity},
                }
                if provider_tools:
                    request_kwargs["tools"] = provider_tools
                return await client.responses.create(**request_kwargs)

            response = await call_with_exponential_backoff(
                create_response,
                service_name="OpenAI",
                logger=logger,
                should_retry=_is_retryable_openai_error,
            )
            return Ok(_parse_openai_response(response, bindings))
        except Exception as e:
            return Err(
                AIServiceError(
                    f"OpenAI API Error: {e}",
                    code="openai_api_error",
                    retryable=_is_retryable_openai_error(e),
                )
            )


def _compose_instructions(
    *,
    system_instruction: str | None,
) -> str:
    return system_instruction or "You are a helpful assistant."


def _positive_int_env(name: str, default: int) -> int:
    """Read a positive integer environment setting with a safe fallback."""

    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        logger.warning("Invalid %s=%r; using default %d", name, raw_value, default)
        return default
    if value <= 0:
        logger.warning("Invalid %s=%r; using default %d", name, raw_value, default)
        return default
    return value


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
