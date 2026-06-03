"""Generated content message DTOs."""

from __future__ import annotations

from pydantic import ConfigDict, Field

from app.contracts.messages.agentic import AgentEnvelope
from app.contracts.messages.tool_contracts import ToolCall


class GeneratedContent(AgentEnvelope):
    """Structured AI output for chat generation."""

    model_config = ConfigDict(extra="forbid")

    agent_context: AgentEnvelope | None = Field(
        default=None,
        description="Legacy agentic envelope metadata bridge for the response.",
    )
    contents: list[str] = Field(description="Generated assistant response texts.")
    tool_calls: list[ToolCall] = Field(
        default_factory=list,
        description="Canonical tool calls requested by the model.",
    )
