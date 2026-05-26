"""Proof-of-concept script for Ollama web search."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import error, request

DEFAULT_API_BASE = "https://ollama.com/api"


@dataclass(frozen=True)
class WebSearchResult:
    """Normalized web search result."""

    title: str
    url: str
    content: str


def _require_api_key() -> str:
    """Return the Ollama API key or fail with a clear message."""
    api_key = os.getenv("OLLAMA_API_KEY")
    if api_key is None or api_key.strip() == "":
        raise SystemExit(
            "OLLAMA_API_KEY is required. Create an Ollama account and API key first."
        )
    return api_key


def _post_json(api_path: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Send a POST request to an Ollama web API endpoint."""
    api_key = _require_api_key()
    url = f"{DEFAULT_API_BASE}/{api_path.lstrip('/')}"
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    try:
        with request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code} calling {url}: {body}") from exc
    except error.URLError as exc:
        raise SystemExit(f"Failed to reach {url}: {exc.reason}") from exc

    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise SystemExit("Unexpected response shape from Ollama API.")
    return parsed


def web_search(query: str, max_results: int = 5) -> list[WebSearchResult]:
    """Search the web using Ollama's web search API."""
    response = _post_json(
        "web_search",
        {"query": query, "max_results": max_results},
    )
    results = response.get("results", [])
    if not isinstance(results, list):
        raise SystemExit("Unexpected results payload from Ollama web search.")

    normalized: list[WebSearchResult] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        url = str(item.get("url", "")).strip()
        content = str(item.get("content", "")).strip()
        if title == "" and url == "" and content == "":
            continue
        normalized.append(
            WebSearchResult(
                title=title,
                url=url,
                content=content,
            )
        )
    return normalized


def web_fetch(url: str) -> dict[str, Any]:
    """Fetch a web page using Ollama's web fetch API."""
    response = _post_json("web_fetch", {"url": url})
    return response


def build_parser() -> argparse.ArgumentParser:
    """Build the command line parser."""
    parser = argparse.ArgumentParser(
        description="Validate Ollama web search and fetch APIs."
    )
    parser.add_argument(
        "query",
        nargs="?",
        default="What is Ollama web search?",
        help="Search query to send to Ollama web search.",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=3,
        choices=range(1, 11),
        help="Maximum number of search results to print.",
    )
    parser.add_argument(
        "--fetch-first",
        action="store_true",
        help="Fetch the first search result with the web fetch API.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the proof-of-concept workflow."""
    parser = build_parser()
    args = parser.parse_args(argv)

    results = web_search(args.query, max_results=args.max_results)

    print(f"Query: {args.query}")
    print(f"Results: {len(results)}")
    for index, result in enumerate(results, start=1):
        print(f"{index}. {result.title}")
        print(f"   {result.url}")
        if result.content != "":
            preview = result.content.replace("\n", " ").strip()
            print(f"   {preview[:280]}")

    if args.fetch_first and results:
        first_url = results[0].url
        if first_url == "":
            print("First result has no URL, skipping fetch.")
            return 0
        fetched = web_fetch(first_url)
        print("Fetched page:")
        print(json.dumps(fetched, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
