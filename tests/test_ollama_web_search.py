from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from scripts.ollama_web_search import WebSearchResult, main, web_search


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
        "scripts.ollama_web_search._post_json",
        return_value=response,
    ):
        actual = web_search("query", max_results=3)

    assert actual == expected


def test_post_json_uses_ollama_api_base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read = Mock(return_value=b'{"ok": true}')

    urlopen = Mock(return_value=response)
    monkeypatch.setenv("OLLAMA_API_KEY", "test-key")
    monkeypatch.setenv("OLLAMA_API_BASE", "https://example.test/api/")

    with patch("scripts.ollama_web_search.request.urlopen", urlopen):
        result = web_search("query", max_results=2)

    assert result == []
    request_obj = urlopen.call_args.args[0]
    assert request_obj.full_url == "https://example.test/api/web_search"
    assert request_obj.headers["Authorization"] == "Bearer test-key"
    assert request_obj.headers["Content-type"] == "application/json"


def test_main_prints_search_results(capsys: pytest.CaptureFixture[str]) -> None:
    fake_results = [
        WebSearchResult(
            title="Ollama",
            url="https://ollama.com",
            content="Search and fetch web content.",
        )
    ]
    with patch("scripts.ollama_web_search.web_search", return_value=fake_results):
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
        patch("scripts.ollama_web_search.web_search", return_value=fake_results),
        patch("scripts.ollama_web_search.web_fetch", return_value=fake_fetch),
    ):
        exit_code = main(["hello", "--fetch-first"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Fetched page:" in captured.out
    assert '"title": "Ollama"' in captured.out
