"""Generic tool contract message DTOs."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.messages.agentic import AgentEnvelope

ToolSideEffect = Literal["none", "read", "write", "send_message"]
ToolExecutionStatus = Literal["ok", "error"]
ToolContinuation = Literal["reenter", "terminal"]
ToolArguments = dict[str, Any]


class SearchToolArguments(BaseModel):
    """Arguments for a search-like tool request."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(description="Search query to execute.")
    max_results: int | None = Field(
        default=None,
        description="Maximum number of results to request.",
    )
    source_request_id: str | None = Field(
        default=None,
        description="Optional source request identifier for search flows.",
    )


class ToolDefinition(BaseModel):
    """Tool metadata surfaced to the agent runtime."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Stable tool identifier.")
    description: str = Field(description="Human-readable tool description.")
    arguments_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON-schema-like arguments contract for the tool.",
    )
    result_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON-schema-like result contract for the tool.",
    )
    capability_scope: list[str] = Field(
        default_factory=list,
        description="Capability scope required to invoke the tool.",
    )
    side_effect: ToolSideEffect = Field(
        default="none",
        description="Observed side effect class for the tool.",
    )
    timeout_seconds: int | None = Field(
        default=None,
        description="Execution timeout in seconds.",
    )
    max_calls_per_run: int | None = Field(
        default=None,
        description="Maximum calls permitted in one agent run.",
    )


class ToolCall(AgentEnvelope):
    """Generic request for a single tool execution."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(description="Requested tool name.")
    arguments: ToolArguments = Field(
        default_factory=dict,
        description="Tool arguments encoded as JSON-compatible data.",
    )


class ToolExecutionResult(AgentEnvelope):
    """Generic result for a single tool execution."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(description="Executed tool name.")
    status: ToolExecutionStatus = Field(description="Execution status.")
    result: ToolArguments = Field(
        default_factory=dict,
        description="Structured execution result payload.",
    )
    error: str | None = Field(
        default=None,
        description="Human-readable execution error.",
    )
    error_code: str | None = Field(
        default=None,
        description="Stable machine-readable error code.",
    )
    rendered_text: str | None = Field(
        default=None,
        description="Prompt-ready representation of the structured result.",
    )


def render_tool_definitions(tool_definitions: list[ToolDefinition]) -> str:
    """Render tool definitions into a prompt-friendly text block."""

    payload = [
        {
            "name": tool.name,
            "description": tool.description,
            "arguments_schema": tool.arguments_schema,
            "result_schema": tool.result_schema,
            "capability_scope": tool.capability_scope,
            "side_effect": tool.side_effect,
            "timeout_seconds": tool.timeout_seconds,
            "max_calls_per_run": tool.max_calls_per_run,
        }
        for tool in tool_definitions
    ]
    return "\n".join(
        [
            "Available tools (JSON):",
            json.dumps(payload, ensure_ascii=False, indent=2),
        ]
    )
