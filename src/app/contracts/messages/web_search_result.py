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
