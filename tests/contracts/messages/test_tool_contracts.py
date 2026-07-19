from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts.messages import (
    GeneratedContent,
    SearchToolArguments,
    ToolCall,
    ToolResultContext,
    normalize_reply_contents,
)


def test_search_tool_arguments_shape() -> None:
    arguments = SearchToolArguments(
        query="ollama web search",
        max_results=3,
        source_request_id="req-1",
    )

    assert arguments.query == "ollama web search"
    assert arguments.max_results == 3
    assert arguments.source_request_id == "req-1"


def test_reply_contents_preserve_message_units_and_line_breaks() -> None:
    arguments = {
        "contents": [
            "first message",
            "second message\nwith a paragraph line break",
        ]
    }

    assert normalize_reply_contents(arguments) == arguments["contents"]


def test_reply_contents_require_the_plural_argument() -> None:
    assert normalize_reply_contents({"content": "legacy message"}) is None


def test_tool_result_context_uses_tool_call_id() -> None:
    context = ToolResultContext(
        tool_call_id="tool-1",
        character_id="reina",
        tool_name="web_search",
        status="ok",
        rendered_text="## Retrieved Context\n- example",
    )

    assert context.tool_call_id == "tool-1"
    assert context.rendered_text.startswith("## Retrieved Context")


def test_generated_content_uses_tool_calls_as_the_only_tool_request_shape() -> None:
    content = GeneratedContent(
        contents=["searching"],
        tool_calls=[
            ToolCall(
                tool_call_id="tool-2",
                character_id="reina",
                tool_name="web_search",
                arguments={
                    "query": "ollama web search",
                    "max_results": 3,
                    "source_request_id": "req-2",
                },
            ),
            ToolCall(
                character_id="reina",
                tool_name="memory.read",
                arguments={"memory_id": "entity:memory-lookup"},
            ),
        ],
    )

    assert len(content.tool_calls) == 2
    assert content.tool_calls[0].tool_call_id == "tool-2"
    assert content.tool_calls[0].tool_name == "web_search"
    assert content.tool_calls[1].tool_name == "memory.read"


@pytest.mark.parametrize(
    "payload",
    [
        [{"id": "call_1", "name": "line.send", "arguments": {}}],
        [{"contents": [], "tool_calls": []}],
        {"contents": "single string"},
    ],
)
def test_generated_content_rejects_noncanonical_payloads(
    payload: object,
) -> None:
    with pytest.raises(ValidationError):
        GeneratedContent.model_validate(payload)
