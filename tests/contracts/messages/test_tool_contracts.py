from __future__ import annotations

from app.contracts.messages import (
    CHAT_TOOL_COMPLETED_TOPIC,
    CHAT_TOOL_REQUESTED_TOPIC,
    AgentEnvelope,
    GeneratedContent,
    SearchToolArguments,
    ToolCall,
    ToolResultContext,
    build_chat_tool_completed_payload,
    build_chat_tool_requested_payload,
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
                event_id="event-2",
                agent_run_id="run-2",
                agent_turn_id="turn-2",
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


def test_generated_content_normalizes_legacy_tool_call_arrays() -> None:
    payload = [
        {
            "id": "call_1",
            "name": "line.send",
            "arguments": {
                "contents": ["こんにちは。"],
            },
        }
    ]

    content = GeneratedContent.model_validate(payload)

    assert content.contents == []
    assert len(content.tool_calls) == 1
    assert content.tool_calls[0].tool_call_id == "call_1"
    assert content.tool_calls[0].tool_name == "line.send"
    assert content.tool_calls[0].arguments == {"contents": ["こんにちは。"]}


def test_generated_content_normalizes_single_item_wrapper_with_tool_calls() -> None:
    payload = [
        {
            "contents": [],
            "tool_calls": [
                {
                    "id": "call_1",
                    "name": "memory.read",
                    "arguments": {
                        "memory_id": "entity:memory-lookup",
                    },
                }
            ],
        }
    ]

    content = GeneratedContent.model_validate(payload)

    assert content.contents == []
    assert len(content.tool_calls) == 1
    assert content.tool_calls[0].tool_call_id == "call_1"
    assert content.tool_calls[0].tool_name == "memory.read"


def test_generated_content_normalizes_scalar_contents_into_a_list() -> None:
    payload = {
        "contents": "ええ、よくわかります。夕暮れ時は一日の疲れが出始める頃です。",
    }

    content = GeneratedContent.model_validate(payload)

    assert content.contents == [
        "ええ、よくわかります。夕暮れ時は一日の疲れが出始める頃です。"
    ]
    assert content.tool_calls == []


def test_generic_tool_payload_builders_merge_agent_metadata() -> None:
    agent_envelope = AgentEnvelope(
        event_id="event-3",
        correlation_id="corr-3",
        causation_id="caus-3",
        agent_run_id="run-3",
        agent_turn_id="turn-3",
        character_id="reina",
        tool_call_id="tool-3",
        source_message_id="msg-3",
        decision_summary="Tool loop bridge",
    )

    requested_payload = build_chat_tool_requested_payload(
        chat_id="chat-1",
        user_id="user-1",
        chat_type="discord",
        tool_call_id="tool-3",
        tool_name="web_search",
        guild_id="DM",
        channel_id="123",
        agent_envelope=agent_envelope,
    )
    completed_payload = build_chat_tool_completed_payload(
        chat_id="chat-1",
        chat_type="discord",
        user_id="user-1",
        status="ok",
        tool_name="web_search",
        continuation="reenter",
        result={"tool_call_id": "tool-3", "retrieved_context": True},
        guild_id="DM",
        channel_id="123",
        agent_envelope=agent_envelope,
    )

    assert requested_payload.get("agent_run_id") == "run-3"
    assert requested_payload.get("character_id") == "reina"
    assert requested_payload.get("tool_call_id") == "tool-3"
    assert "arguments" not in requested_payload
    assert completed_payload["status"] == "ok"
    result = completed_payload.get("result")
    assert result is not None
    assert result["retrieved_context"] is True
    assert completed_payload.get("decision_summary") == "Tool loop bridge"
    assert completed_payload.get("character_id") == "reina"
    assert CHAT_TOOL_REQUESTED_TOPIC == "chat.tool.requested"
    assert CHAT_TOOL_COMPLETED_TOPIC == "chat.tool.completed"
