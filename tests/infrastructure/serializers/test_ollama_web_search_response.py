"""Tests for Ollama web search response normalization."""

from flow_res import is_err

from app.infrastructure.serializers.ollama_web_search_response import (
    parse_ollama_web_search_response,
)


def test_parse_ollama_web_search_response_returns_typed_result() -> None:
    result = parse_ollama_web_search_response(
        {
            "results": [
                {
                    "title": "Example",
                    "url": "https://example.com",
                    "content": "Retrieved text",
                    "score": "0.75",
                }
            ]
        }
    )

    assert not is_err(result)
    assert result.value.items[0].title == "Example"
    assert result.value.items[0].score == 0.75


def test_parse_ollama_web_search_response_rejects_invalid_results() -> None:
    result = parse_ollama_web_search_response({"results": {}})

    assert is_err(result)
    assert result.error.message == "Response results must be a list."
