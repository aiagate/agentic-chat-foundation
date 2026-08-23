"""Gemini service implementation."""

import json
import logging
import os
from typing import Any, cast

from flow_res import Err, Ok, Result
from google import genai
from google.genai import types
from pydantic import ValidationError

from app.contracts.messages.ai_continuation import AIContinuation
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
_DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"
_DEFAULT_GEMINI_THINKING_LEVEL = types.ThinkingLevel.MEDIUM


class GeminiResponseError(ValueError):
    """A completed Gemini response that is unsafe to expose as an answer."""


def _parse_generated_content(payload: Any) -> GeneratedContent:
    """Parse structured Gemini output into the DTO."""
    if isinstance(payload, str):
        loaded_payload = json.loads(payload)
        return _parse_generated_content(loaded_payload)
    try:
        return GeneratedContent.model_validate(payload)
    except ValidationError:
        return GeneratedContent(contents=[json.dumps(payload, ensure_ascii=False)])


def _gemini_tools(bindings: list[ProviderToolBinding]) -> list[types.Tool]:
    """Translate canonical tools into Gemini function declarations."""

    if not bindings:
        return []
    declarations = [
        types.FunctionDeclaration(
            name=binding.alias,
            description=binding.definition.description,
            parameters_json_schema=binding.definition.arguments_schema,
        )
        for binding in bindings
    ]
    return [types.Tool(function_declarations=declarations)]


def _gemini_function_calls(
    content: types.Content,
    bindings: list[ProviderToolBinding],
) -> list[ToolCall]:
    """Normalize Gemini native function calls into canonical tool calls."""

    tool_calls: list[ToolCall] = []
    for part in content.parts or []:
        raw_call = part.function_call
        if raw_call is None:
            continue
        provider_name = raw_call.name
        arguments = raw_call.args
        if not isinstance(provider_name, str) or not isinstance(arguments, dict):
            raise GeminiResponseError("Gemini returned an invalid function call")
        tool_name = canonical_tool_name(provider_name, bindings)
        if tool_name is None:
            raise GeminiResponseError(
                f"Gemini returned an unknown tool: {provider_name}"
            )
        tool_calls.append(
            ToolCall(
                tool_call_id=raw_call.id,
                tool_name=tool_name,
                arguments=arguments,
            )
        )
    return tool_calls


def _finished_content(response: Any) -> types.Content:
    """Return the sole safe candidate content or reject the response."""

    candidates = getattr(response, "candidates", None)
    if not isinstance(candidates, list) or len(candidates) != 1:
        raise GeminiResponseError("Gemini returned no unique candidate")
    candidate = candidates[0]
    finish_reason = getattr(candidate, "finish_reason", None)
    if finish_reason != types.FinishReason.STOP:
        reason = getattr(finish_reason, "value", finish_reason)
        raise GeminiResponseError(f"Gemini stopped with finish reason: {reason}")
    content = getattr(candidate, "content", None)
    if not isinstance(content, types.Content):
        raise GeminiResponseError("Gemini returned no candidate content")
    return content


def _visible_text(content: types.Content) -> str:
    """Join visible text parts without exposing thought parts."""

    return "".join(
        part.text
        for part in content.parts or []
        if part.text is not None and part.thought is not True
    ).strip()


def _continuation_content(continuation: AIContinuation) -> types.Content:
    if continuation.provider != "gemini":
        raise ValueError("Continuation state belongs to a different provider")
    return types.Content.model_validate_json(continuation.payload)


def _function_response_content(
    previous_content: types.Content,
    bindings: list[ProviderToolBinding],
    tool_results: list[ToolResultContext],
) -> types.Content:
    calls = [
        part.function_call
        for part in previous_content.parts or []
        if part.function_call is not None
    ]
    if len(calls) != len(tool_results) or not calls:
        raise ValueError("Gemini continuation tool result count does not match")

    parts: list[types.Part] = []
    for call, result in zip(calls, tool_results, strict=True):
        provider_name = call.name
        if not isinstance(provider_name, str):
            raise ValueError("Gemini continuation contains an unnamed function call")
        canonical_name = canonical_tool_name(provider_name, bindings)
        if canonical_name != result.tool_name:
            raise ValueError("Gemini continuation tool name does not match")
        if call.id is not None and result.tool_call_id != call.id:
            raise ValueError("Gemini continuation tool call ID does not match")
        if result.status == "ok":
            response_payload: dict[str, Any] = {
                "output": {
                    "result": result.result,
                    "rendered_text": result.rendered_text,
                }
            }
        else:
            response_payload = {
                "error": {
                    "message": result.error or "Tool execution failed",
                    "result": result.result,
                    "rendered_text": result.rendered_text,
                }
            }
        parts.append(
            types.Part(
                function_response=types.FunctionResponse(
                    id=call.id,
                    name=provider_name,
                    response=response_payload,
                )
            )
        )
    return types.Content(role="user", parts=parts)


class GeminiService(IAIService):
    """Implementation using Google Gemini."""

    def __init__(self) -> None:
        api_key = os.getenv("GEMINI_API_KEY")
        self._model = os.getenv("GEMINI_MODEL", _DEFAULT_GEMINI_MODEL)
        self._client = genai.Client(api_key=api_key) if api_key else None

    async def generate_content(
        self,
        prompt: str,
        history: list[ChatHistoryItem],
        system_instruction: str | None = None,
        tool_definitions: list[ToolDefinition] | None = None,
        tool_results: list[ToolResultContext] | None = None,
        continuation: AIContinuation | None = None,
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
            current_prompt = render_agent_prompt(prompt=prompt, tool_results=[])
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
                    "tool_result_count": len(tool_results or []),
                    "continuation": continuation is not None,
                    "contents": _serialize_gemini_contents(messages, current_prompt),
                    "tool_definitions": serialize_tool_definitions(tool_definitions),
                },
            )
            config = types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(
                    thinking_level=_DEFAULT_GEMINI_THINKING_LEVEL,
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

            request_contents = messages + [
                types.Content(
                    role="user",
                    parts=[types.Part(text=current_prompt)],
                )
            ]
            if continuation is not None:
                previous_content = _continuation_content(continuation)
                function_responses = _function_response_content(
                    previous_content,
                    bindings,
                    tool_results or [],
                )
                request_contents.extend([previous_content, function_responses])
            elif tool_results:
                raise ValueError("Gemini tool results require continuation state")

            response = await call_with_exponential_backoff(
                lambda: client.aio.models.generate_content(
                    model=self._model,
                    contents=cast(
                        list[types.ContentOrDict],
                        request_contents,
                    ),
                    config=config,
                ),
                service_name="Gemini",
                logger=logger,
            )
            content = _finished_content(response)
            native_tool_calls = _gemini_function_calls(content, bindings)
            candidate = cast(list[Any], response.candidates)[0]
            finish_reason = candidate.finish_reason
            usage = getattr(response, "usage_metadata", None)
            logger.info(
                "Gemini response completed: model=%s response_id=%s finish_reason=%s "
                "tool_calls=%s prompt_tokens=%s output_tokens=%s thought_tokens=%s "
                "total_tokens=%s",
                self._model,
                getattr(response, "response_id", None),
                getattr(finish_reason, "value", finish_reason),
                len(native_tool_calls),
                getattr(usage, "prompt_token_count", None),
                getattr(usage, "candidates_token_count", None),
                getattr(usage, "thoughts_token_count", None),
                getattr(usage, "total_token_count", None),
            )
            if native_tool_calls:
                return Ok(
                    GeneratedContent(
                        tool_calls=native_tool_calls,
                        continuation=AIContinuation(
                            provider="gemini",
                            payload=content.model_dump_json(
                                by_alias=True,
                                exclude_none=True,
                            ),
                        ),
                    )
                )

            if provider_tools:
                text = _visible_text(content)
                if not text:
                    raise GeminiResponseError("Gemini returned empty text output")
                return Ok(GeneratedContent(contents=[text]))

            parsed_payload = response.parsed
            if parsed_payload is None:
                parsed_payload = _visible_text(content)
            parsed_content = _parse_generated_content(parsed_payload)
            if not parsed_content.contents and response.parsed is not None:
                parsed_content = _parse_generated_content(_visible_text(content))
            if not parsed_content.contents or parsed_content.tool_calls:
                raise GeminiResponseError("Gemini returned invalid structured output")
            return Ok(GeneratedContent(contents=parsed_content.contents))
        except GeminiResponseError as e:
            logger.warning(
                "Gemini response rejected: model=%s reason=%s", self._model, e
            )
            return Err(
                AIServiceError(
                    "Gemini returned an incomplete response.",
                    code="gemini_invalid_response",
                    retryable=False,
                )
            )
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
