"""Ollama web search adapter."""

from __future__ import annotations

import json
import os
from urllib import error, request

from flow_res import Err, Result

from app.contracts.messages.tool_contracts import SearchToolArguments
from app.contracts.messages.web_search_result import WebSearchResult
from app.contracts.ports.web_search_service import (
    IWebSearchService,
    WebSearchServiceError,
)
from app.infrastructure.serializers.ollama_web_search_response import (
    parse_ollama_web_search_response,
)


class OllamaWebSearchService(IWebSearchService):
    """Search the web through Ollama's web search API."""

    def __init__(self) -> None:
        self._api_key = os.getenv("OLLAMA_API_KEY")
        self._api_base = os.getenv("OLLAMA_API_BASE", "https://ollama.com/api")

    async def search(
        self,
        arguments: SearchToolArguments,
    ) -> Result[WebSearchResult, WebSearchServiceError]:
        if self._api_key is None or self._api_key.strip() == "":
            return Err(WebSearchServiceError("OLLAMA_API_KEY is required."))

        payload = {"query": arguments.query, "max_results": arguments.max_results}
        url = f"{self._api_base.rstrip('/')}/web_search"
        req = request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )

        try:
            with request.urlopen(req, timeout=30) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return Err(WebSearchServiceError(f"HTTP {exc.code}: {body}"))
        except error.URLError as exc:
            return Err(WebSearchServiceError(f"Failed to reach Ollama: {exc.reason}"))

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            return Err(WebSearchServiceError(f"Invalid JSON response: {exc}"))
        return parse_ollama_web_search_response(parsed)
