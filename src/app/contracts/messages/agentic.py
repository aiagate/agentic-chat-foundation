"""Agentic workflow message DTOs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AgentEnvelope(BaseModel):
    """Optional agentic correlation metadata shared across messages."""

    model_config = ConfigDict(extra="forbid")

    event_id: str | None = Field(
        default=None,
        description="Event identifier for the payload carrying this envelope.",
    )
    correlation_id: str | None = Field(
        default=None,
        description="Correlation identifier tying the user request to the run.",
    )
    causation_id: str | None = Field(
        default=None,
        description="Immediate parent event identifier.",
    )
    agent_run_id: str | None = Field(
        default=None,
        description="Identifier for the agent workflow run.",
    )
    agent_turn_id: str | None = Field(
        default=None,
        description="Identifier for one LLM inference turn.",
    )
    character_id: str | None = Field(
        default=None,
        description="Identifier for the active agent character.",
    )
    tool_call_id: str | None = Field(
        default=None,
        description="Identifier for one tool call within a turn.",
    )
    source_message_id: str | None = Field(
        default=None,
        description="Originating platform message identifier.",
    )
    decision_summary: str | None = Field(
        default=None,
        description="Observable summary of why the turn or call was made.",
    )
