"""Short-lived tool result context for agent re-entry."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ToolResultContext(BaseModel):
    """Normalized tool result supplied to a subsequent agent turn."""

    model_config = ConfigDict(extra="forbid")

    tool_call_id: str = Field(description="Tool call that produced this result.")
    character_id: str = Field(description="Agent character that owns this result.")
    tool_name: str = Field(description="Tool that produced this result.")
    status: Literal["ok", "error"] = Field(description="Tool execution status.")
    result: dict[str, object] = Field(default_factory=dict)
    error: str | None = None
    rendered_text: str = Field(description="Prompt-ready tool result text.")
