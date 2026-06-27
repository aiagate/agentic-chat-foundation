"""Helpers for assembling one agent-turn runtime context."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from flow_res import is_err

from app.contracts.messages.conversation_context import (
    ConversationContext,
    render_conversation_context,
)
from app.contracts.messages.llm_request_context import (
    LLMCurrentInput,
    LLMRequestContext,
)
from app.contracts.messages.memory_context import MemoryContextPack
from app.contracts.messages.tool_contracts import ToolDefinition
from app.contracts.messages.tool_result_context import ToolResultContext
from app.contracts.ports.tool_result_store import IToolResultStore
from app.domain.value_objects.chat_type import ChatType

logger = logging.getLogger(__name__)


async def build_turn_llm_request_context(
    *,
    tool_result_store: IToolResultStore,
    conversation_context: ConversationContext,
    memory_context: MemoryContextPack,
    persona_context: str,
    prompt: str,
    character_id: str,
    tool_call_id: str | None,
    tool_failure_context: str | None,
) -> LLMRequestContext:
    """Assemble the system instruction and follow-up search policy."""

    system_parts = [
        persona_context,
        render_conversation_context(conversation_context),
        output_contract_instruction(),
    ]

    tool_result = await _load_tool_result(
        tool_result_store,
        tool_call_id=tool_call_id,
        character_id=character_id,
    )
    current_input = LLMCurrentInput(kind="message", content=prompt)
    if tool_result is not None:
        current_input = LLMCurrentInput(
            kind="tool_result",
            content=_render_tool_result_input(tool_result),
        )
    elif tool_failure_context is not None:
        current_input = LLMCurrentInput(
            kind="tool_result",
            content=_render_tool_failure_input(tool_failure_context),
        )

    return LLMRequestContext(
        system_prompt=join_context(system_parts),
        tool_definitions=[],
        memory_context=memory_context.assembled_context,
        recent_history=[],
        current_input=current_input,
    )


def filter_tool_definitions(
    tool_definitions: list[ToolDefinition],
    *,
    chat_type: ChatType,
) -> list[ToolDefinition]:
    """Expose only the tools that make sense for the current chat type."""

    allowed_tool_names = {"memory.read", "memory.write_candidate", "web_search"}
    match chat_type:
        case ChatType.LINE:
            allowed_tool_names.add("line.send")
        case ChatType.DISCORD:
            allowed_tool_names.add("discord.send")

    filtered_tools = [
        tool for tool in tool_definitions if tool.name in allowed_tool_names
    ]
    return filtered_tools


def join_context(parts: Sequence[str | None]) -> str | None:
    """Join prompt sections while skipping empty segments."""

    rendered = [part for part in parts if part]
    if not rendered:
        return None
    return "\n\n".join(rendered)


def output_contract_instruction() -> str:
    """Describe the strict JSON output contract expected from the model."""

    return (
        "Output contract:\n"
        "- Return a single JSON object that matches GeneratedContent.\n"
        "- Each item in contents is delivered as one message to the current conversation.\n"
        "- A response may contain both contents and tool_calls.\n"
        "- Put tool requests in tool_calls.\n"
        "- Divide contents into natural conversational message units."
    )


def _render_tool_result_input(tool_result: ToolResultContext) -> str:
    guidance = [
        "Tool result received.",
        "Use the tool result and recent conversation to answer the user's latest request directly.",
    ]
    guidance.append("")
    guidance.append(tool_result.rendered_text)
    return "\n".join(guidance)


def _render_tool_failure_input(tool_failure_context: str) -> str:
    return "\n".join(
        [
            "Tool result received with an error.",
            "Use the available context to provide the next useful response.",
            "",
            tool_failure_context,
        ]
    )


async def _load_tool_result(
    tool_result_store: IToolResultStore,
    *,
    tool_call_id: str | None,
    character_id: str,
) -> ToolResultContext | None:
    if tool_call_id is None:
        return None
    tool_result = await tool_result_store.get(
        tool_call_id,
        character_id=character_id,
    )
    if is_err(tool_result):
        logger.warning(
            "Tool result unavailable for tool call %s: %s",
            tool_call_id,
            tool_result.error,
        )
        return None
    return tool_result.value
