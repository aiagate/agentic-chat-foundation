"""Minimal CLI wrapper around the Ollama web_search endpoint."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any
from urllib import request


@dataclass(frozen=True, slots=True)
class WebSearchResult:
    """Normalized search result returned by the CLI."""

    title: str
    url: str
    content: str


def _api_base() -> str:
    base = os.getenv("OLLAMA_API_BASE", "http://localhost:11434/api/")
    return base.rstrip("/") + "/"


def _api_key() -> str | None:
    value = os.getenv("OLLAMA_API_KEY")
    return value.strip() if value and value.strip() else None


def _post_json(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = _api_base() + path.lstrip("/")
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    api_key = _api_key()
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    with request.urlopen(req) as response:
        return json.loads(response.read().decode("utf-8"))


def web_search(query: str, *, max_results: int = 5) -> list[WebSearchResult]:
    """Execute a web search request and normalize the result list."""

    payload = _post_json("web_search", {"query": query, "max_results": max_results})
    results = payload.get("results", [])
    normalized: list[WebSearchResult] = []
    if not isinstance(results, list):
        return normalized
    for item in results:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", ""))
        url = str(item.get("url", ""))
        content = str(item.get("content", ""))
        normalized.append(WebSearchResult(title=title, url=url, content=content))
    return normalized


def web_fetch(url: str) -> dict[str, Any]:
    """Fetch a page through the Ollama web_fetch endpoint."""

    return _post_json("web_fetch", {"url": url})


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for manual web search experiments."""

    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--max-results", type=int, default=5)
    parser.add_argument("--fetch-first", action="store_true")
    args = parser.parse_args(argv)

    results = web_search(args.query, max_results=args.max_results)
    print(f"Query: {args.query}")
    for index, result in enumerate(results, start=1):
        print(f"{index}. {result.title} - {result.url}")
        if result.content:
            print(result.content)

    if args.fetch_first and results:
        print("Fetched page:")
        print(json.dumps(web_fetch(results[0].url), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
