"""Translate Ollama web search responses into application messages."""

from __future__ import annotations

from flow_res import Err, Ok, Result

from app.contracts.messages.web_search_result import (
    WebSearchResult,
    WebSearchResultItem,
)
from app.contracts.ports.web_search_service import WebSearchServiceError


def parse_ollama_web_search_response(
    payload: object,
) -> Result[WebSearchResult, WebSearchServiceError]:
    """Validate and normalize one Ollama web search response."""
    if not isinstance(payload, dict):
        return Err(WebSearchServiceError("Unexpected response shape."))
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        return Err(WebSearchServiceError("Response results must be a list."))

    items: list[WebSearchResultItem] = []
    for raw_item in raw_results:
        if not isinstance(raw_item, dict):
            return Err(WebSearchServiceError("Response result item must be an object."))
        content = raw_item.get("content")
        items.append(
            WebSearchResultItem(
                title=_optional_text(raw_item.get("title")),
                url=_optional_text(raw_item.get("url")),
                snippet="" if content is None else str(content),
                content=_optional_text(content),
                score=_optional_float(raw_item.get("score")),
            )
        )
    return Ok(WebSearchResult(items=items))


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None
