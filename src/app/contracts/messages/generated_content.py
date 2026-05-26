"""Generated content message DTOs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.messages.tool_use import ToolUseRequest


class GeneratedContent(BaseModel):
    """Structured AI output for chat generation."""

    model_config = ConfigDict(extra="forbid")

    contents: list[str] = Field(description="Generated assistant response texts.")
    tool_use_request: ToolUseRequest | None = Field(
        default=None,
        description="Optional external tool request.",
    )
