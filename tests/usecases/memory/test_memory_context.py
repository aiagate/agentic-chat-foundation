"""Tests for memory use cases."""

from typing import Any

import pytest
from flow_res import Err, Ok, is_err

from app.contracts.messages.chat_history import ChatHistoryItem
from app.contracts.messages.memory_context import MemoryContextPack
from app.contracts.ports.memory_service import IMemoryService
from app.domain.value_objects.chat_type import ChatType
from app.usecases.memory.retrieve_memory_context import (
    RetrieveMemoryContextHandler,
    RetrieveMemoryContextQuery,
)


@pytest.fixture
def mock_memory_service(mocker: Any) -> IMemoryService:
    service = mocker.Mock(spec=IMemoryService)
    service.retrieve = mocker.AsyncMock(return_value=Ok(_memory_context_pack()))
    return service


@pytest.mark.anyio
async def test_retrieve_memory_context_success(
    mock_memory_service: Any,
) -> None:
    """Test retrieving a memory context through the port."""
    handler = RetrieveMemoryContextHandler(mock_memory_service)

    result = await handler.handle(
        RetrieveMemoryContextQuery(history=[], prompt="hello", user_id="u1")
    )

    assert not is_err(result)
    assert result.value.user_id == "u1"
    mock_memory_service.retrieve.assert_awaited_once_with("hello", "u1")


@pytest.mark.anyio
async def test_retrieve_memory_context_failure(
    mocker: Any,
) -> None:
    """Test retrieval error mapping."""
    memory_service = mocker.Mock(spec=IMemoryService)
    memory_service.retrieve = mocker.AsyncMock(
        return_value=Err(Exception("memory error"))
    )
    handler = RetrieveMemoryContextHandler(memory_service)

    result = await handler.handle(
        RetrieveMemoryContextQuery(history=[], prompt="hello", user_id="u1")
    )

    assert is_err(result)
    memory_service.retrieve.assert_awaited_once_with("hello", "u1")


@pytest.mark.anyio
async def test_retrieve_memory_context_builds_recent_bundle_query(
    mocker: Any,
) -> None:
    """Test that the use case builds a recent-history retrieval query."""

    memory_service = mocker.Mock(spec=IMemoryService)
    memory_service.retrieve = mocker.AsyncMock(return_value=Ok(_memory_context_pack()))
    handler = RetrieveMemoryContextHandler(memory_service)
    history = [
        ChatHistoryItem(
            id=f"chat-{index}",
            user_id="u1",
            chat_type=ChatType.DISCORD,
            role="user",
            content=f"message-{index}",
            occurred_at=None,
        )
        for index in range(1, 11)
    ]

    result = await handler.handle(
        RetrieveMemoryContextQuery(
            history=history,
            prompt="message-11",
            user_id="u1",
        )
    )

    assert not is_err(result)
    memory_service.retrieve.assert_awaited_once_with(
        "\n".join(
            [
                "message-4",
                "message-5",
                "message-6",
                "message-7",
                "message-8",
                "message-9",
                "message-10",
                "message-11",
            ]
        ),
        "u1",
    )


def _memory_context_pack() -> MemoryContextPack:
    return MemoryContextPack(user_id="u1")
