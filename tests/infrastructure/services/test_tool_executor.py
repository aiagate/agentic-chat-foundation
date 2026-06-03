"""Tests for the generic tool executor adapter."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from flow_res import Ok, is_err

from app.contracts.messages.chat_events import (
    DISCORD_CHAT_REPLY_READY_TOPIC,
    LINE_CHAT_REPLY_READY_TOPIC,
)
from app.contracts.messages.memory_context import (
    MemoryContextFrame,
    MemoryContextPack,
    MemoryEntity,
    MemoryFrameSection,
    MemoryProfile,
    MemorySearchHit,
    MemorySource,
    MemoryTimelineEntry,
)
from app.contracts.messages.retrieved_context import (
    RetrievedContext,
)
from app.contracts.messages.tool_contracts import ToolCall
from app.contracts.ports.event_bus import IEventBus
from app.contracts.ports.memory_service import IMemoryService
from app.contracts.ports.memory_write_service import IMemoryWriteService
from app.contracts.ports.retrieved_context_store import IRetrievedContextStore
from app.contracts.ports.tool_executor import ToolExecutionContext
from app.domain.value_objects.chat_type import ChatType
from app.infrastructure.services.tool_executor import GenericToolExecutor


@pytest.fixture
def event_bus(mocker: Any) -> IEventBus:
    bus = mocker.Mock(spec=IEventBus)
    bus.publish = mocker.AsyncMock(return_value=None)
    return bus


@pytest.fixture
def memory_service(mocker: Any) -> IMemoryService:
    service = mocker.Mock(spec=IMemoryService)
    service.retrieve = mocker.AsyncMock(return_value=Ok(_memory_context_pack()))
    return service


@pytest.fixture
def memory_write_service(mocker: Any) -> IMemoryWriteService:
    service = mocker.Mock(spec=IMemoryWriteService)
    service.add_log = mocker.AsyncMock(return_value=Ok(None))
    return service


@pytest.fixture
def retrieved_context_store(mocker: Any) -> IRetrievedContextStore:
    store = mocker.Mock(spec=IRetrievedContextStore)
    store.save = mocker.AsyncMock(return_value=Ok(None))
    return store


@pytest.mark.anyio
async def test_generic_tool_executor_web_search_runs_search(
    event_bus: IEventBus,
    memory_service: IMemoryService,
    memory_write_service: IMemoryWriteService,
    retrieved_context_store: IRetrievedContextStore,
    mocker: Any,
) -> None:
    """web_search should execute the search use case and persist context."""

    mocker.patch(
        "app.infrastructure.services.tool_executor.Mediator.send_async",
        new=AsyncMock(return_value=Ok(type("R", (), {"result_count": 3})())),
    )

    executor = GenericToolExecutor(
        event_bus=event_bus,
        retrieved_context_store=retrieved_context_store,
        memory_service=memory_service,
        memory_write_service=memory_write_service,
    )
    context = ToolExecutionContext(
        chat_id="chat-1",
        user_id="u1",
        chat_type=ChatType.DISCORD,
        tool_call=ToolCall(
            tool_name="web_search",
            arguments={"query": "search query", "max_results": 3},
            user_message="searching",
            tool_call_id="tool-1",
        ),
        guild_id="DM",
        channel_id="123",
    )

    result = await executor.execute(context)

    assert not is_err(result)
    assert result.value.result["tool_call_id"] == "tool-1"
    assert result.value.result["retrieved_context"] is True
    assert result.value.result["query"] == "search query"


@pytest.mark.anyio
async def test_generic_tool_executor_memory_search_saves_context(
    event_bus: IEventBus,
    memory_service: IMemoryService,
    memory_write_service: IMemoryWriteService,
    retrieved_context_store: IRetrievedContextStore,
) -> None:
    """memory.search should persist a retrieved context for the tool call."""

    executor = GenericToolExecutor(
        event_bus=event_bus,
        retrieved_context_store=retrieved_context_store,
        memory_service=memory_service,
        memory_write_service=memory_write_service,
    )
    context = ToolExecutionContext(
        chat_id="chat-1",
        user_id="u1",
        chat_type=ChatType.DISCORD,
        tool_call=ToolCall(
            tool_name="memory.search",
            arguments={"query": "memory lookup"},
            user_message="searching memory",
            tool_call_id="tool-1",
        ),
        guild_id="DM",
        channel_id="123",
    )

    result = await executor.execute(context)

    assert not is_err(result)
    assert result.value.result["tool_call_id"] == "tool-1"
    assert result.value.result["retrieved_context"] is True
    assert result.value.result["result_count"] == 1
    save_mock = cast(Any, retrieved_context_store.save)
    save_mock.assert_awaited_once()
    saved_context = cast(RetrievedContext, save_mock.await_args.args[0])
    assert saved_context.tool_call_id == "tool-1"
    assert saved_context.tool_name == "memory.search"
    assert saved_context.query == "memory lookup"
    assert saved_context.rendered_text.startswith("Memory Context")


@pytest.mark.anyio
async def test_generic_tool_executor_line_reply_publishes_reply_ready(
    event_bus: IEventBus,
    memory_service: IMemoryService,
    memory_write_service: IMemoryWriteService,
    retrieved_context_store: IRetrievedContextStore,
) -> None:
    """line.reply should publish a LINE reply-ready event."""

    executor = GenericToolExecutor(
        event_bus=event_bus,
        retrieved_context_store=retrieved_context_store,
        memory_service=memory_service,
        memory_write_service=memory_write_service,
    )
    context = ToolExecutionContext(
        chat_id="chat-1",
        user_id="u1",
        chat_type=ChatType.LINE,
        tool_call=ToolCall(
            tool_name="line.reply",
            arguments={"content": "hello"},
            user_message="reply",
        ),
    )

    result = await executor.execute(context)

    assert not is_err(result)
    assert result.value.result["content_count"] == 1
    publish_mock = cast(Any, event_bus.publish)
    publish_mock.assert_awaited_once()
    topic, payload = publish_mock.await_args.args
    assert topic == LINE_CHAT_REPLY_READY_TOPIC
    assert payload["contents"] == ["hello"]
    assert payload["user_id"] == "u1"


@pytest.mark.anyio
async def test_generic_tool_executor_discord_post_channel_publishes_reply_ready(
    event_bus: IEventBus,
    memory_service: IMemoryService,
    memory_write_service: IMemoryWriteService,
    retrieved_context_store: IRetrievedContextStore,
) -> None:
    """discord.post_channel should publish to the requested Discord channel."""

    executor = GenericToolExecutor(
        event_bus=event_bus,
        retrieved_context_store=retrieved_context_store,
        memory_service=memory_service,
        memory_write_service=memory_write_service,
    )
    context = ToolExecutionContext(
        chat_id="chat-1",
        user_id="u1",
        chat_type=ChatType.DISCORD,
        tool_call=ToolCall(
            tool_name="discord.post_channel",
            arguments={
                "target_channel_id": "999",
                "contents": ["hello", "world"],
            },
            user_message="post",
        ),
        guild_id="guild-1",
        channel_id="123",
    )

    result = await executor.execute(context)

    assert not is_err(result)
    assert result.value.result["channel_id"] == "999"
    assert result.value.result["content_count"] == 2
    publish_mock = cast(Any, event_bus.publish)
    publish_mock.assert_awaited_once()
    topic, payload = publish_mock.await_args.args
    assert topic == DISCORD_CHAT_REPLY_READY_TOPIC
    assert payload["channel_id"] == "999"
    assert payload["contents"] == ["hello", "world"]


@pytest.mark.anyio
async def test_generic_tool_executor_rejects_line_reply_in_discord_chat(
    event_bus: IEventBus,
    memory_service: IMemoryService,
    memory_write_service: IMemoryWriteService,
    retrieved_context_store: IRetrievedContextStore,
) -> None:
    """line.reply must not execute in a Discord chat context."""

    executor = GenericToolExecutor(
        event_bus=event_bus,
        retrieved_context_store=retrieved_context_store,
        memory_service=memory_service,
        memory_write_service=memory_write_service,
    )
    context = ToolExecutionContext(
        chat_id="chat-1",
        user_id="u1",
        chat_type=ChatType.DISCORD,
        tool_call=ToolCall(
            tool_name="line.reply",
            arguments={"content": "hello"},
            user_message="reply",
        ),
        guild_id="guild-1",
        channel_id="123",
    )

    result = await executor.execute(context)

    assert is_err(result)
    publish_mock = cast(Any, event_bus.publish)
    publish_mock.assert_not_awaited()


@pytest.mark.anyio
async def test_generic_tool_executor_rejects_discord_post_channel_in_line_chat(
    event_bus: IEventBus,
    memory_service: IMemoryService,
    memory_write_service: IMemoryWriteService,
    retrieved_context_store: IRetrievedContextStore,
) -> None:
    """discord.post_channel must not execute in a LINE chat context."""

    executor = GenericToolExecutor(
        event_bus=event_bus,
        retrieved_context_store=retrieved_context_store,
        memory_service=memory_service,
        memory_write_service=memory_write_service,
    )
    context = ToolExecutionContext(
        chat_id="chat-1",
        user_id="U1234567890",
        chat_type=ChatType.LINE,
        tool_call=ToolCall(
            tool_name="discord.post_channel",
            arguments={
                "target_channel_id": "999",
                "content": "hello",
            },
            user_message="post",
        ),
    )

    result = await executor.execute(context)

    assert is_err(result)
    publish_mock = cast(Any, event_bus.publish)
    publish_mock.assert_not_awaited()


@pytest.mark.anyio
async def test_generic_tool_executor_memory_write_candidate_writes_log(
    event_bus: IEventBus,
    memory_service: IMemoryService,
    memory_write_service: IMemoryWriteService,
    retrieved_context_store: IRetrievedContextStore,
) -> None:
    """memory.write_candidate should flow through the write port."""

    executor = GenericToolExecutor(
        event_bus=event_bus,
        retrieved_context_store=retrieved_context_store,
        memory_service=memory_service,
        memory_write_service=memory_write_service,
    )
    context = ToolExecutionContext(
        chat_id="chat-1",
        user_id="u1",
        chat_type=ChatType.DISCORD,
        tool_call=ToolCall(
            tool_name="memory.write_candidate",
            arguments={
                "content": "remember this",
                "role": "assistant",
                "metadata": {"source": "tool"},
            },
            user_message="write memory",
            tool_call_id="tool-1",
            decision_summary="persist useful note",
        ),
        guild_id="guild-1",
        channel_id="123",
    )

    result = await executor.execute(context)

    assert not is_err(result)
    assert result.value.result["written"] is True
    add_log_mock = cast(Any, memory_write_service.add_log)
    add_log_mock.assert_awaited_once()
    await_args = add_log_mock.await_args
    assert await_args.kwargs["user_id"] == "u1"
    assert await_args.kwargs["role"] == "assistant"
    assert await_args.kwargs["content"] == "remember this"
    assert await_args.kwargs["metadata"]["chat_id"] == "chat-1"
    assert await_args.kwargs["metadata"]["tool_name"] == "memory.write_candidate"
    assert await_args.kwargs["metadata"]["source"] == "tool"


def _memory_context_pack() -> MemoryContextPack:
    return MemoryContextPack(
        user_id="u1",
        assembled_context="Memory Context:\n## Primary\nUse concise answers.",
        context_frame=MemoryContextFrame(
            assembled_context="Memory Context:\n## Primary\nUse concise answers.",
            sections=[
                MemoryFrameSection(
                    name="primary",
                    content="Use concise answers.",
                    sources=[
                        MemorySource(
                            id="profile:u1",
                            memory_type="profile",
                            title="Dorothy",
                            user_id="u1",
                            reference="profile:u1",
                        )
                    ],
                )
            ],
        ),
        profile=MemoryProfile(
            user_id="u1",
            display_name="Dorothy",
            summary="Likes concise answers.",
            traits=["pragmatic"],
            preferences=["short replies"],
        ),
        timelines=[
            MemoryTimelineEntry(
                id="timeline-1",
                user_id="u1",
                kind="message",
                content="Remember the short answer preference.",
                occurred_at="2026-05-11T00:00:00Z",
                source="chat",
                entity_ids=[],
                metadata={},
            )
        ],
        entities=[
            MemoryEntity(
                id="entity-1",
                user_id="u1",
                label="desktop app",
                entity_type="project",
                status="active",
                aliases=["app"],
                attributes={},
                confidence=0.9,
            )
        ],
        search_hits=[
            MemorySearchHit(
                source=MemorySource(
                    id="source-1",
                    memory_type="timeline",
                    title="Timeline hit",
                    user_id="u1",
                    reference="timeline-1",
                ),
                score=0.9,
                matched_terms=["memory"],
                excerpt="Memory hit",
            )
        ],
    )
