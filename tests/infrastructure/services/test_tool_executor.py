"""Tests for non-terminal generic tool execution adapters."""

from typing import Any, cast

import pytest
from flow_res import Err, Ok, is_err

from app.contracts.messages.chat_type import ChatType
from app.contracts.messages.memory_context import MemoryReadResult, MemorySource
from app.contracts.messages.tool_contracts import ToolCall
from app.contracts.messages.web_search_result import (
    WebSearchResult,
    WebSearchResultItem,
)
from app.contracts.ports.memory_service import IMemoryService
from app.contracts.ports.tool_executor import ToolExecutionContext
from app.contracts.ports.web_search_service import (
    IWebSearchService,
    WebSearchServiceError,
)
from app.infrastructure.services.tool_executor import GenericToolExecutor

CHARACTER_ID = "shirasagi-reina"


@pytest.fixture
def memory_service(mocker: Any) -> IMemoryService:
    service = mocker.Mock(spec=IMemoryService)
    service.read_memory = mocker.AsyncMock(return_value=Ok(_memory_read_result()))
    return service


@pytest.fixture
def web_search_service(mocker: Any) -> IWebSearchService:
    service = mocker.Mock(spec=IWebSearchService)
    service.search = mocker.AsyncMock(
        return_value=Ok(
            WebSearchResult(
                items=[
                    WebSearchResultItem(snippet=f"result {index}") for index in range(3)
                ]
            )
        )
    )
    return service


def _executor(
    memory_service: IMemoryService,
    web_search_service: IWebSearchService,
) -> GenericToolExecutor:
    return GenericToolExecutor(
        memory_service=memory_service,
        web_search_service=web_search_service,
    )


def _context(name: str, arguments: dict[str, object]) -> ToolExecutionContext:
    return ToolExecutionContext(
        chat_id="chat-1",
        character_id=CHARACTER_ID,
        user_id="u1",
        chat_type=ChatType.DISCORD,
        tool_call=ToolCall(
            tool_name=name,
            arguments=arguments,
            tool_call_id="tool-1",
            character_id=CHARACTER_ID,
        ),
        guild_id="guild",
        channel_id="channel",
    )


@pytest.mark.anyio
async def test_web_search_returns_structured_and_rendered_result(
    memory_service: IMemoryService,
    web_search_service: IWebSearchService,
) -> None:
    result = await _executor(memory_service, web_search_service).execute(
        _context("web_search", {"query": "search", "max_results": 3})
    )

    assert not is_err(result)
    assert result.value.result["retrieved_context"] is True
    assert result.value.rendered_text is not None
    cast(Any, web_search_service.search).assert_awaited_once()


@pytest.mark.anyio
async def test_memory_read_returns_prompt_ready_text(
    memory_service: IMemoryService,
    web_search_service: IWebSearchService,
) -> None:
    result = await _executor(memory_service, web_search_service).execute(
        _context("memory.read", {"memory_id": "entity:memory-lookup"})
    )

    assert not is_err(result)
    assert result.value.result["result_count"] == 1
    assert result.value.rendered_text == _memory_read_result().rendered_text


@pytest.mark.anyio
async def test_search_failure_is_returned_to_durable_coordinator(
    memory_service: IMemoryService,
    web_search_service: IWebSearchService,
) -> None:
    cast(Any, web_search_service.search).return_value = Err(
        WebSearchServiceError("search failed")
    )
    result = await _executor(memory_service, web_search_service).execute(
        _context("web_search", {"query": "latest"})
    )

    assert is_err(result)
    assert result.error.message == "Failed to execute web search"


@pytest.mark.anyio
async def test_terminal_send_tool_is_not_executed_by_adapter(
    memory_service: IMemoryService,
    web_search_service: IWebSearchService,
) -> None:
    result = await _executor(memory_service, web_search_service).execute(
        _context("unknown_tool", {})
    )

    assert is_err(result)
    assert result.error.message == "Unsupported tool: unknown_tool"


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
