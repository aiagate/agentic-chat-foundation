from __future__ import annotations

import pytest

from app.contracts.messages import (
    RetrievedContext,
    SearchToolArguments,
    ToolUseRequest,
    build_chat_search_completed_payload,
    build_chat_search_requested_payload,
)


def test_tool_use_request_shape() -> None:
    request = ToolUseRequest(
        search_session_id="search-1",
        tool_name="web_search",
        arguments=SearchToolArguments(
            query="ollama web search",
            max_results=3,
            source_request_id="req-1",
        ),
        user_message="ちょっと検索してみます",
    )

    assert request.search_session_id == "search-1"
    assert request.tool_name == "web_search"
    assert request.arguments.query == "ollama web search"
    assert request.user_message == "ちょっと検索してみます"


def test_retrieved_context_shape() -> None:
    context = RetrievedContext(
        search_session_id="search-1",
        query="ollama web search",
        tool_name="web_search",
        items=[],
        rendered_text="## Retrieved Context\n- example",
    )

    assert context.search_session_id == "search-1"
    assert context.rendered_text.startswith("## Retrieved Context")


@pytest.mark.parametrize(
    ("builder", "expected_key"),
    [
        (build_chat_search_requested_payload, "search_session_id"),
        (build_chat_search_completed_payload, "result_count"),
    ],
)
def test_search_event_payload_builders(
    builder: object,
    expected_key: str,
) -> None:
    if builder is build_chat_search_requested_payload:
        payload = build_chat_search_requested_payload(
            search_session_id="search-1",
            source_request_id="req-1",
            chat_id="chat-1",
            user_id="user-1",
            chat_type="discord",
            prompt="hello",
            query="ollama web search",
            tool_name="web_search",
            user_message="ちょっと検索してみます",
            max_results=3,
        )
    else:
        payload = build_chat_search_completed_payload(
            search_session_id="search-1",
            source_request_id="req-1",
            chat_id="chat-1",
            chat_type="discord",
            user_id="user-1",
            prompt="hello",
            status="ok",
            result_count=2,
            tool_name="web_search",
        )

    assert expected_key in payload
