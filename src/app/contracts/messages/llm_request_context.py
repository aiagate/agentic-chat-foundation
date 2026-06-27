"""Structured LLM request context shared across agent layers."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.messages.chat_history import ChatHistoryItem
from app.contracts.messages.tool_contracts import ToolDefinition

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


def compose_system_instruction(context: LLMRequestContext) -> str | None:
    """Flatten structured system-side context for provider APIs."""

    parts = [context.system_prompt, context.memory_context]
    rendered = [part for part in parts if part]
    if not rendered:
        return None
    return "\n\n".join(rendered)
