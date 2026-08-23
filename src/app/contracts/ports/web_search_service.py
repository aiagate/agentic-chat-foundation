"""Web search service port."""

from __future__ import annotations

from abc import ABC, abstractmethod

from flow_res import Result

from app.contracts.messages.tool_contracts import SearchToolArguments
from app.contracts.messages.web_search_result import WebSearchResult


class WebSearchServiceError(Exception):
    """Represents a web search adapter error."""

    message: str

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return self.message


class IWebSearchService(ABC):
    """Search the public web."""

    @abstractmethod
    async def search(
        self,
        arguments: SearchToolArguments,
    ) -> Result[WebSearchResult, WebSearchServiceError]:
        """Search the web and return a normalized payload."""
        raise NotImplementedError
