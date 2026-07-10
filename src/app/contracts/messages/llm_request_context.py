"""Structured LLM request context shared across agent layers."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.messages.chat_history import ChatHistoryItem
from app.contracts.messages.conversation_context import (
    ConversationContext,
    render_conversation_context,
)
from app.contracts.messages.tool_contracts import ToolDefinition
from app.contracts.messages.tool_result_context import ToolResultContext

LLMInputKind = Literal["message", "tool_result"]


class LLMCurrentInput(BaseModel):
    """Current input supplied to the LLM for this turn."""

    model_config = ConfigDict(extra="forbid")

    kind: LLMInputKind = Field(
        description="Whether the input is a user message or tool result."
    )
    content: str = Field(description="Prompt text passed as the current turn input.")


class LLMRequestContext(BaseModel):
    """Structured context categories passed to the LLM."""

    model_config = ConfigDict(extra="forbid")

    system_prompt: str | None = Field(
        default=None,
        description="System prompt that defines persona and runtime rules.",
    )
    tool_definitions: list[ToolDefinition] = Field(
        default_factory=list,
        description="Tool definitions exposed for this turn.",
    )
    memory_context: str | None = Field(
        default=None,
        description="Prompt-ready memory manifest or memory detail context.",
    )
    recent_history: list[ChatHistoryItem] = Field(
        default_factory=list,
        description="Recent conversation history retained for the turn.",
    )
    current_input: LLMCurrentInput = Field(
        description="Newest input item for the turn, either a message or tool result.",
    )


def build_agent_system_prompt(
    persona_context: str,
    conversation_context: ConversationContext,
) -> str:
    """Build the stable system-side instruction for an agent turn."""
    return "\n\n".join(
        [
            persona_context,
            render_conversation_context(conversation_context),
            (
                "Output contract:\n"
                "- Return a single JSON object that matches GeneratedContent.\n"
                "- Each item in contents is delivered as one message to the current "
                "conversation.\n"
                "- A response may contain both contents and tool_calls.\n"
                "- Put tool requests in tool_calls.\n"
                "- Divide contents into natural conversational message units."
            ),
        ]
    )


def build_agent_current_input(
    *,
    prompt: str,
    tool_result: ToolResultContext | None,
    tool_failure_context: str | None,
) -> LLMCurrentInput:
    """Build the current LLM input with tool outcomes taking precedence."""
    if tool_result is not None:
        return LLMCurrentInput(
            kind="tool_result",
            content="\n".join(
                [
                    "Tool result received.",
                    (
                        "Use the tool result and recent conversation to answer the "
                        "user's latest request directly."
                    ),
                    "",
                    tool_result.rendered_text,
                ]
            ),
        )
    if tool_failure_context is not None:
        return LLMCurrentInput(
            kind="tool_result",
            content="\n".join(
                [
                    "Tool result received with an error.",
                    "Use the available context to provide the next useful response.",
                    "",
                    tool_failure_context,
                ]
            ),
        )
    return LLMCurrentInput(kind="message", content=prompt)


def compose_system_instruction(context: LLMRequestContext) -> str | None:
    """Flatten structured system-side context for provider APIs."""

    parts = [context.system_prompt, context.memory_context]
    rendered = [part for part in parts if part]
    if not rendered:
        return None
    return "\n\n".join(rendered)
