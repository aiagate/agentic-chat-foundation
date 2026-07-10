"""Tests for durable AgentRun messages."""

from app.contracts.messages.agent_run import (
    AgentRunSnapshot,
    AgentRunStatus,
    AgentToolCallSnapshot,
    AgentToolCallStatus,
)
from app.contracts.messages.agent_run_events import (
    build_agent_run_wakeup_payload,
    build_agent_tool_requested_payload,
)
from app.contracts.messages.chat_type import ChatType
from app.contracts.messages.tool_contracts import ToolCall


def test_terminal_tool_result_is_available_to_next_turn() -> None:
    tool = AgentToolCallSnapshot(
        id="tool-1",
        agent_run_id="run-1",
        turn_number=1,
        tool_call=ToolCall(
            tool_call_id="tool-1", tool_name="web_search", arguments={"query": "x"}
        ),
        status=AgentToolCallStatus.SUCCEEDED,
        continuation="reenter",
        result={"count": 1},
        rendered_result="search result",
    )
    run = AgentRunSnapshot(
        id="run-1",
        conversation_key="character:DISCORD:guild:channel",
        source_chat_id="chat-1",
        character_id="character",
        user_id="user",
        chat_type=ChatType.DISCORD,
        guild_id="guild",
        channel_id="channel",
        status=AgentRunStatus.READY,
        turn_number=1,
        max_turns=8,
        attempt_count=1,
        wake_sequence=2,
        version=3,
        tool_calls=[tool],
    )

    assert [result.rendered_text for result in run.tool_results] == ["search result"]


def test_transport_payloads_only_contain_durable_identifiers() -> None:
    assert build_agent_run_wakeup_payload(agent_run_id="run", wake_sequence=4) == {
        "agent_run_id": "run",
        "wake_sequence": 4,
    }
    assert build_agent_tool_requested_payload(
        agent_run_id="run", tool_call_id="tool", attempt_count=2
    ) == {"agent_run_id": "run", "tool_call_id": "tool", "attempt_count": 2}
