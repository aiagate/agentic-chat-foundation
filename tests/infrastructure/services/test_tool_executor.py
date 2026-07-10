"""Tests for the generic tool executor adapter."""

from __future__ import annotations

from typing import Any, cast

import pytest
from flow_res import Err, Ok, is_err

from app.contracts.messages.memory_context import (
    MemoryReadResult,
    MemorySource,
)
from app.contracts.messages.tool_contracts import ToolCall
from app.contracts.messages.tool_result_context import ToolResultContext
from app.contracts.messages.web_search_result import (
    WebSearchResult,
    WebSearchResultItem,
)
from app.contracts.ports.agent_reply_writer import IAgentReplyWriter
from app.contracts.ports.memory_service import IMemoryService
from app.contracts.ports.memory_write_service import IMemoryWriteService
from app.contracts.ports.tool_executor import ToolExecutionContext
from app.contracts.ports.tool_result_store import IToolResultStore
from app.contracts.ports.web_search_service import (
    IWebSearchService,
    WebSearchServiceError,
)
from app.domain.value_objects.chat_type import ChatType
from app.infrastructure.services.tool_executor import GenericToolExecutor

CHARACTER_ID = "shirasagi-reina"


@pytest.fixture
def memory_service(mocker: Any) -> IMemoryService:
    service = mocker.Mock(spec=IMemoryService)
    service.read_memory = mocker.AsyncMock(return_value=Ok(_memory_read_result()))
    service.build_context = mocker.AsyncMock(return_value=Ok(type("M", (), {})()))
    return service


@pytest.fixture
def memory_write_service(mocker: Any) -> IMemoryWriteService:
    service = mocker.Mock(spec=IMemoryWriteService)
    service.add_log = mocker.AsyncMock(return_value=Ok(None))
    return service


@pytest.fixture
def tool_result_store(mocker: Any) -> IToolResultStore:
    store = mocker.Mock(spec=IToolResultStore)
    store.save = mocker.AsyncMock(return_value=Ok(None))
    return store


@pytest.fixture
def web_search_service(mocker: Any) -> IWebSearchService:
    service = mocker.Mock(spec=IWebSearchService)
    service.search = mocker.AsyncMock(
        return_value=Ok(
            WebSearchResult(
                items=[
                    WebSearchResultItem(snippet=f"result {index}")
                    for index in range(3)
                ]
            )
        )
    )
    return service


@pytest.fixture
def agent_reply_writer(mocker: Any) -> IAgentReplyWriter:
    writer = mocker.Mock(spec=IAgentReplyWriter)
    writer.write = mocker.AsyncMock(return_value=Ok(None))
    return writer


@pytest.mark.anyio
async def test_generic_tool_executor_web_search_runs_search(
    memory_service: IMemoryService,
    memory_write_service: IMemoryWriteService,
    tool_result_store: IToolResultStore,
    web_search_service: IWebSearchService,
    agent_reply_writer: IAgentReplyWriter,
) -> None:
    """web_search should call the search port and persist context."""

    executor = GenericToolExecutor(
        tool_result_store=tool_result_store,
        memory_service=memory_service,
        memory_write_service=memory_write_service,
        web_search_service=web_search_service,
        agent_reply_writer=agent_reply_writer,
    )
    context = ToolExecutionContext(
        chat_id="chat-1",
        character_id=CHARACTER_ID,
        user_id="u1",
        chat_type=ChatType.DISCORD,
        tool_call=ToolCall(
            tool_name="web_search",
            arguments={"query": "search query", "max_results": 3},
            tool_call_id="tool-1",
            character_id=CHARACTER_ID,
        ),
        guild_id="DM",
        channel_id="123",
    )

    result = await executor.execute(context)

    assert not is_err(result)
    assert result.value.result["tool_call_id"] == "tool-1"
    assert result.value.result["retrieved_context"] is True
    assert result.value.result["query"] == "search query"
    search_mock = cast(Any, web_search_service.search)
    search_mock.assert_awaited_once()


@pytest.mark.anyio
async def test_generic_tool_executor_memory_read_saves_context(
    memory_service: IMemoryService,
    memory_write_service: IMemoryWriteService,
    tool_result_store: IToolResultStore,
    web_search_service: IWebSearchService,
    agent_reply_writer: IAgentReplyWriter,
) -> None:
    """memory.read should persist a retrieved context for the tool call."""

    executor = GenericToolExecutor(
        tool_result_store=tool_result_store,
        memory_service=memory_service,
        memory_write_service=memory_write_service,
        web_search_service=web_search_service,
        agent_reply_writer=agent_reply_writer,
    )
    context = ToolExecutionContext(
        chat_id="chat-1",
        character_id=CHARACTER_ID,
        user_id="u1",
        chat_type=ChatType.DISCORD,
        tool_call=ToolCall(
            tool_name="memory.read",
            arguments={"memory_id": "entity:memory-lookup"},
            tool_call_id="tool-1",
            character_id=CHARACTER_ID,
        ),
        guild_id="DM",
        channel_id="123",
    )

    result = await executor.execute(context)

    assert not is_err(result)
    assert result.value.result["tool_call_id"] == "tool-1"
    assert result.value.result["retrieved_context"] is True
    assert result.value.result["result_count"] == 1
    save_mock = cast(Any, tool_result_store.save)
    save_mock.assert_awaited_once()
    saved_context = cast(ToolResultContext, save_mock.await_args.args[0])
    assert saved_context.tool_call_id == "tool-1"
    assert saved_context.tool_name == "memory.read"
    assert saved_context.rendered_text.startswith("## Memory: entity:memory-lookup")


@pytest.mark.anyio
async def test_generic_tool_executor_memory_write_candidate_writes_log(
    memory_service: IMemoryService,
    memory_write_service: IMemoryWriteService,
    tool_result_store: IToolResultStore,
    web_search_service: IWebSearchService,
    agent_reply_writer: IAgentReplyWriter,
) -> None:
    """memory.write_candidate should flow through the write port."""

    executor = GenericToolExecutor(
        tool_result_store=tool_result_store,
        memory_service=memory_service,
        memory_write_service=memory_write_service,
        web_search_service=web_search_service,
        agent_reply_writer=agent_reply_writer,
    )
    context = ToolExecutionContext(
        chat_id="chat-1",
        character_id=CHARACTER_ID,
        user_id="u1",
        chat_type=ChatType.DISCORD,
        tool_call=ToolCall(
            tool_name="memory.write_candidate",
            arguments={
                "content": "remember this",
                "role": "assistant",
                "metadata": {"source": "tool"},
            },
            tool_call_id="tool-1",
            decision_summary="persist useful note",
            character_id=CHARACTER_ID,
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


@pytest.mark.anyio
async def test_generic_tool_executor_line_send_writes_reply(
    memory_service: IMemoryService,
    memory_write_service: IMemoryWriteService,
    tool_result_store: IToolResultStore,
    web_search_service: IWebSearchService,
    agent_reply_writer: IAgentReplyWriter,
) -> None:
    executor = GenericToolExecutor(
        tool_result_store=tool_result_store,
        memory_service=memory_service,
        memory_write_service=memory_write_service,
        web_search_service=web_search_service,
        agent_reply_writer=agent_reply_writer,
    )
    context = ToolExecutionContext(
        chat_id="chat-1",
        character_id=CHARACTER_ID,
        user_id="line-user",
        chat_type=ChatType.LINE,
        tool_call=ToolCall(
            tool_name="line.send",
            arguments={"contents": ["hello", "world"]},
            tool_call_id="tool-1",
            character_id=CHARACTER_ID,
        ),
    )

    result = await executor.execute(context)

    assert not is_err(result)
    assert result.value.result == {"content_count": 2}
    write_mock = cast(Any, agent_reply_writer.write)
    write_mock.assert_awaited_once()
    request = write_mock.await_args.args[0]
    assert request.guild_id == "LINE"
    assert request.channel_id == "line-user"
    assert request.contents == ["hello", "world"]
    save_mock = cast(Any, tool_result_store.save)
    save_mock.assert_not_awaited()


@pytest.mark.anyio
async def test_generic_tool_executor_rejects_cross_platform_send(
    memory_service: IMemoryService,
    memory_write_service: IMemoryWriteService,
    tool_result_store: IToolResultStore,
    web_search_service: IWebSearchService,
    agent_reply_writer: IAgentReplyWriter,
) -> None:
    executor = GenericToolExecutor(
        tool_result_store=tool_result_store,
        memory_service=memory_service,
        memory_write_service=memory_write_service,
        web_search_service=web_search_service,
        agent_reply_writer=agent_reply_writer,
    )
    context = ToolExecutionContext(
        chat_id="chat-1",
        character_id=CHARACTER_ID,
        user_id="line-user",
        chat_type=ChatType.LINE,
        tool_call=ToolCall(
            tool_name="discord.send",
            arguments={"contents": ["hello"]},
            tool_call_id="tool-1",
            character_id=CHARACTER_ID,
        ),
    )

    result = await executor.execute(context)

    assert is_err(result)
    assert result.error.message == "discord.send is only available for Discord chats"
    write_mock = cast(Any, agent_reply_writer.write)
    write_mock.assert_not_awaited()


@pytest.mark.anyio
async def test_generic_tool_executor_stores_non_send_failure(
    memory_service: IMemoryService,
    memory_write_service: IMemoryWriteService,
    tool_result_store: IToolResultStore,
    web_search_service: IWebSearchService,
    agent_reply_writer: IAgentReplyWriter,
) -> None:
    search_mock = cast(Any, web_search_service.search)
    search_mock.return_value = Err(WebSearchServiceError("search failed"))
    executor = GenericToolExecutor(
        tool_result_store=tool_result_store,
        memory_service=memory_service,
        memory_write_service=memory_write_service,
        web_search_service=web_search_service,
        agent_reply_writer=agent_reply_writer,
    )
    context = ToolExecutionContext(
        chat_id="chat-1",
        character_id=CHARACTER_ID,
        user_id="user-1",
        chat_type=ChatType.DISCORD,
        tool_call=ToolCall(
            tool_name="web_search",
            arguments={"query": "latest"},
            tool_call_id="tool-1",
            character_id=CHARACTER_ID,
        ),
    )

    result = await executor.execute(context)

    assert is_err(result)
    save_mock = cast(Any, tool_result_store.save)
    save_mock.assert_awaited_once()
    saved_context = cast(ToolResultContext, save_mock.await_args.args[0])
    assert saved_context.status == "error"
    assert saved_context.error == "Failed to execute web search"


def _memory_read_result() -> MemoryReadResult:
    return MemoryReadResult(
        memory_id="entity:memory-lookup",
        source=MemorySource(
            id="memory-lookup",
            memory_type="entity",
            title="Dorothy",
            user_id="u1",
            reference="entities/u1/memory-lookup.md",
        ),
        title="Dorothy",
        summary="Likes concise answers.",
        rendered_text="## Memory: entity:memory-lookup\nUse concise answers.",
    )
