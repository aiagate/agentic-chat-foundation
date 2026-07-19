"""Structured LLM request context shared across agent layers."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.messages.chat_history import ChatHistoryItem
from app.contracts.messages.conversation_context import (
    ConversationContext,
    render_conversation_context,
)
from app.contracts.messages.tool_contracts import ToolDefinition
from app.contracts.messages.tool_result_context import ToolResultContext


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
    prompt: str = Field(
        description="Authoritative user request for the whole agent run.",
    )
    tool_results: list[ToolResultContext] = Field(
        default_factory=list,
        description="Additional observations collected while answering the request.",
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
                "- Answer the user's current request directly when no tool is needed.\n"
                "- Use only the tools exposed by the provider when external context "
                "or an application action is needed.\n"
                "- Do not describe a tool request as ordinary reply text.\n"
                "- Use the current conversation's send-message tool when the reply "
                "must be divided into multiple message units.\n"
                "- For a direct LINE/DM reply, use 2 to 4 natural sentences, avoid "
                "headings, bullet lists, Markdown, and formal closings.\n"
                "- Acknowledge one specific feeling, then offer at most one ordinary "
                "next step or question. Prefer everyday Japanese over clinical or "
                "business terms.\n"
                "- Do not propose symptom logs, self-assessment, or a consultation "
                "plan for ordinary low mood. Do not add a routine medical-provider "
                "or helpline recommendation. If there is clear imminent danger, "
                "prioritize brief safety guidance."
            ),
        ]
    )


def render_agent_prompt(
    *,
    prompt: str,
    tool_results: list[ToolResultContext] | tuple[ToolResultContext, ...],
) -> str:
    """Render one stable user request with observations collected for it."""
    if not tool_results:
        return prompt
    rendered_results = "\n\n".join(
        f"[{result.tool_name}]\n{result.rendered_text}" for result in tool_results
    )
    return "\n".join(
        [
            "User request:",
            prompt,
            "",
            "Tool results collected for this request:",
            rendered_results,
            "",
            "Answer the user request using these results.",
        ]
    )


def compose_system_instruction(context: LLMRequestContext) -> str | None:
    """Flatten structured system-side context for provider APIs."""

    parts = [context.system_prompt, context.memory_context]
    rendered = [part for part in parts if part]
    if not rendered:
        return None
    return "\n\n".join(rendered)
