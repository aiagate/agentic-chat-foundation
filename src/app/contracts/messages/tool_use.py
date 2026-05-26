"""Tool request message DTOs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ToolName = Literal["web_search"]


class SearchToolArguments(BaseModel):
    """Arguments for a web search tool request."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(description="Search query to execute.")
    max_results: int | None = Field(
        default=None,
        description="Maximum number of results to request.",
    )
    source_request_id: str | None = Field(
        default=None,
        description="Source request identifier for tracing.",
    )


class ToolUseRequest(BaseModel):
    """Structured request for executing an external tool."""

    model_config = ConfigDict(extra="forbid")

    search_session_id: str = Field(description="Search workflow session ID.")
    tool_name: ToolName = Field(description="Requested tool name.")
    arguments: SearchToolArguments = Field(description="Tool call arguments.")
    user_message: str = Field(
        description="Message to show the user while the tool runs.",
    )
