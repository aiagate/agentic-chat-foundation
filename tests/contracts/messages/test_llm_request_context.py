"""Tests for provider-ready agent request rendering."""

from app.contracts.messages.llm_request_context import render_agent_prompt
from app.contracts.messages.tool_result_context import ToolResultContext


def _tool_result(
    *,
    tool_call_id: str,
    tool_name: str,
    status: str,
    rendered_text: str,
) -> ToolResultContext:
    return ToolResultContext.model_validate(
        {
            "tool_call_id": tool_call_id,
            "character_id": "reina",
            "tool_name": tool_name,
            "status": status,
            "rendered_text": rendered_text,
        }
    )


def test_render_agent_prompt_returns_original_request_without_tool_results() -> None:
    prompt = "土日横浜周辺で何かイベントないですかね"

    assert render_agent_prompt(prompt=prompt, tool_results=[]) == prompt


def test_render_agent_prompt_keeps_request_with_web_search_result() -> None:
    prompt = "土日横浜周辺で何かイベントないですかね"

    rendered = render_agent_prompt(
        prompt=prompt,
        tool_results=[
            _tool_result(
                tool_call_id="search-1",
                tool_name="web_search",
                status="ok",
                rendered_text="横浜の週末イベント",
            )
        ],
    )

    assert prompt in rendered
    assert "[web_search]\n横浜の週末イベント" in rendered
    assert rendered.index(prompt) < rendered.index("横浜の週末イベント")


def test_render_agent_prompt_keeps_request_with_multiple_and_failed_results() -> None:
    prompt = "最新情報を確認してください"

    rendered = render_agent_prompt(
        prompt=prompt,
        tool_results=[
            _tool_result(
                tool_call_id="search-1",
                tool_name="web_search",
                status="ok",
                rendered_text="検索結果",
            ),
            _tool_result(
                tool_call_id="memory-1",
                tool_name="memory.read",
                status="error",
                rendered_text="memory.read failed: not found",
            ),
        ],
    )

    assert rendered.count(prompt) == 1
    assert "[web_search]\n検索結果" in rendered
    assert "[memory.read]\nmemory.read failed: not found" in rendered
