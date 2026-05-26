from __future__ import annotations

from unittest.mock import patch

import pytest

from poc.ollama_web_search_poc import WebSearchResult, main, web_search


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ({"results": []}, []),
        (
            {"results": [{"title": "A", "url": "https://example.com", "content": "C"}]},
            [WebSearchResult(title="A", url="https://example.com", content="C")],
        ),
    ],
)
def test_web_search_normalizes_results(
    response: dict[str, object], expected: list[WebSearchResult]
) -> None:
    with patch(
        "poc.ollama_web_search_poc._post_json",
        return_value=response,
    ):
        actual = web_search("query", max_results=3)

    assert actual == expected


def test_main_prints_search_results(capsys: pytest.CaptureFixture[str]) -> None:
    fake_results = [
        WebSearchResult(
            title="Ollama",
            url="https://ollama.com",
            content="Search and fetch web content.",
        )
    ]
    with patch("poc.ollama_web_search_poc.web_search", return_value=fake_results):
        exit_code = main(["hello", "--max-results", "1"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Query: hello" in captured.out
    assert "1. Ollama" in captured.out


def test_main_fetches_first_result(capsys: pytest.CaptureFixture[str]) -> None:
    fake_results = [
        WebSearchResult(
            title="Ollama",
            url="https://ollama.com",
            content="Search and fetch web content.",
        )
    ]
    fake_fetch = {"title": "Ollama", "content": "Body", "links": []}
    with (
        patch("poc.ollama_web_search_poc.web_search", return_value=fake_results),
        patch("poc.ollama_web_search_poc.web_fetch", return_value=fake_fetch),
    ):
        exit_code = main(["hello", "--fetch-first"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Fetched page:" in captured.out
    assert '"title": "Ollama"' in captured.out
