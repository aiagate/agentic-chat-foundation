"""Normalized web search result messages."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class WebSearchResultItem(BaseModel):
    """Single normalized web search result."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, description="Result title.")
    url: str | None = Field(default=None, description="Source URL.")
    snippet: str = Field(description="Short retrieved snippet.")
    content: str | None = Field(default=None, description="Longer result content.")
    score: float | None = Field(default=None, description="Optional ranking score.")


class WebSearchResult(BaseModel):
    """Provider-independent web search result."""

    model_config = ConfigDict(extra="forbid")

    items: list[WebSearchResultItem] = Field(default_factory=list)

    def render_retrieved_context(self, tool_call_id: str) -> str:
        """Render the result as prompt context for a tool call."""
        lines = [
            "## Retrieved Context",
            f"- tool_call_id: {tool_call_id}",
        ]
        for item in self.items:
            lines.append(f"- title: {item.title or '(untitled)'}")
            if item.url:
                lines.append(f"  url: {item.url}")
            lines.append(f"  snippet: {item.snippet}")
        return "\n".join(lines)
