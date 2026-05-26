"""Retrieved context message DTOs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.messages.tool_use import ToolName


class RetrievedContextItem(BaseModel):
    """Single retrieved search result item."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, description="Result title.")
    url: str | None = Field(default=None, description="Source URL.")
    snippet: str = Field(description="Short retrieved snippet.")
    content: str | None = Field(
        default=None,
        description="Optional longer retrieved content.",
    )
    score: float | None = Field(
        default=None,
        description="Optional ranking score.",
    )


class RetrievedContext(BaseModel):
    """Explicitly labeled context block for re-prompting the LLM."""

    model_config = ConfigDict(extra="forbid")

    search_session_id: str = Field(description="Search workflow session ID.")
    query: str = Field(description="Search query that produced this context.")
    tool_name: ToolName = Field(description="Tool that produced the context.")
    items: list[RetrievedContextItem] = Field(
        default_factory=list,
        description="Retrieved search items.",
    )
    rendered_text: str = Field(
        description="Prompt-ready rendered retrieved context block.",
    )
