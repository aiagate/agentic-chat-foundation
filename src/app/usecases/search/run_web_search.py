"""Execute a web search and render its result."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from flow_med import Request, RequestHandler
from flow_res import Err, Ok, Result, is_err
from injector import inject

from app.contracts.messages.tool_contracts import SearchToolArguments
from app.contracts.messages.web_search_result import WebSearchResultItem
from app.contracts.ports.web_search_service import IWebSearchService
from app.usecases.result import ErrorType, UseCaseError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunWebSearchResult:
    """Search execution metadata."""

    result_count: int
    rendered_text: str


@dataclass
class RunWebSearchCommand(Request[Result[RunWebSearchResult, UseCaseError]]):
    """Run a web search for an existing tool call."""

    tool_call_id: str
    query: str
    source_request_id: str
    character_id: str
    tool_name: Literal["web_search"] = "web_search"
    max_results: int | None = None


class RunWebSearchHandler(
    RequestHandler[RunWebSearchCommand, Result[RunWebSearchResult, UseCaseError]]
):
    """Handle web search execution."""

    @inject
    def __init__(
        self,
        web_search_service: IWebSearchService,
    ) -> None:
        self._web_search_service = web_search_service

    async def handle(
        self, request: RunWebSearchCommand
    ) -> Result[RunWebSearchResult, UseCaseError]:
        """Execute search and return prompt-ready result text."""
        search_result = await self._web_search_service.search(
            SearchToolArguments(
                query=request.query,
                max_results=request.max_results,
                source_request_id=request.source_request_id,
            )
        )
        if is_err(search_result):
            return Err(
                UseCaseError(
                    type=ErrorType.UNEXPECTED,
                    message="Failed to execute web search",
                )
            )

        payload = search_result.value
        items = _normalize_items(payload.get("results", []))
        rendered_text = _render_retrieved_context(request.tool_call_id, items)
        logger.info(
            "Web search completed: tool_call_id=%s result_count=%d",
            request.tool_call_id,
            len(items),
        )

        return Ok(
            RunWebSearchResult(
                result_count=len(items),
                rendered_text=rendered_text,
            )
        )


def _normalize_items(raw_results: object) -> list[WebSearchResultItem]:
    items: list[WebSearchResultItem] = []
    if not isinstance(raw_results, list):
        return items
    for raw_item in raw_results:
        if not isinstance(raw_item, dict):
            continue
        items.append(
            WebSearchResultItem(
                title=_as_str_or_none(raw_item.get("title")),
                url=_as_str_or_none(raw_item.get("url")),
                snippet=_as_str(raw_item.get("content")),
                content=_as_str_or_none(raw_item.get("content")),
                score=_as_float_or_none(raw_item.get("score")),
            )
        )
    return items


def _render_retrieved_context(
    tool_call_id: str,
    items: list[WebSearchResultItem],
) -> str:
    lines = [
        "## Retrieved Context",
        f"- tool_call_id: {tool_call_id}",
    ]
    for item in items:
        title = item.title or "(untitled)"
        lines.append(f"- title: {title}")
        if item.url:
            lines.append(f"  url: {item.url}")
        lines.append(f"  snippet: {item.snippet}")
    return "\n".join(lines)


def _as_str(value: object) -> str:
    return "" if value is None else str(value)


def _as_str_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text != "" else None


def _as_float_or_none(value: object) -> float | None:
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
