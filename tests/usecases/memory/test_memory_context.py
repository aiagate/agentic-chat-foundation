"""Tests for memory use cases."""

from typing import Any, cast

import pytest
from flow_res import Err, Ok, is_err

from app.contracts.messages.memory_context import MemoryContextPack
from app.contracts.ports.memory_service import IMemoryService
from app.usecases.memory.append_memory_log import (
    AppendMemoryLogCommand,
    AppendMemoryLogHandler,
)
from app.usecases.memory.retrieve_memory_context import (
    RetrieveMemoryContextHandler,
    RetrieveMemoryContextQuery,
)


@pytest.fixture
def mock_memory_service(mocker: Any) -> IMemoryService:
    service = mocker.Mock(spec=IMemoryService)
    service.retrieve = mocker.AsyncMock(return_value=Ok(_memory_context_pack()))
    service.add_log = mocker.AsyncMock(return_value=Ok(None))
    return service


@pytest.mark.anyio
async def test_retrieve_memory_context_success(
    mock_memory_service: IMemoryService,
) -> None:
    """Test retrieving a memory context through the port."""
    handler = RetrieveMemoryContextHandler(mock_memory_service)

    result = await handler.handle(
        RetrieveMemoryContextQuery(query="hello", user_id="u1")
    )

    assert not is_err(result)
    assert result.value.user_id == "u1"
    retrieve_stub = cast(Any, mock_memory_service.retrieve)
    retrieve_stub.assert_awaited_once_with("hello", "u1")


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
        RetrieveMemoryContextQuery(query="hello", user_id="u1")
    )

    assert is_err(result)
    memory_service.retrieve.assert_awaited_once_with("hello", "u1")


@pytest.mark.anyio
async def test_append_memory_log_success(
    mock_memory_service: IMemoryService,
) -> None:
    """Test appending a raw memory log through the port."""
    handler = AppendMemoryLogHandler(mock_memory_service)

    result = await handler.handle(
        AppendMemoryLogCommand(
            user_id="u1",
            role="assistant",
            content="hello",
            metadata={"chat_type": "DISCORD"},
        )
    )

    assert not is_err(result)
    add_log_stub = cast(Any, mock_memory_service.add_log)
    add_log_stub.assert_awaited_once_with(
        "u1",
        "assistant",
        "hello",
        {"chat_type": "DISCORD"},
    )


@pytest.mark.anyio
async def test_append_memory_log_failure(
    mocker: Any,
) -> None:
    """Test append error mapping."""
    memory_service = mocker.Mock(spec=IMemoryService)
    memory_service.add_log = mocker.AsyncMock(
        return_value=Err(Exception("memory error"))
    )
    handler = AppendMemoryLogHandler(memory_service)

    result = await handler.handle(
        AppendMemoryLogCommand(
            user_id="u1",
            role="assistant",
            content="hello",
            metadata={"chat_type": "DISCORD"},
        )
    )

    assert is_err(result)
    memory_service.add_log.assert_awaited_once_with(
        "u1",
        "assistant",
        "hello",
        {"chat_type": "DISCORD"},
    )


def _memory_context_pack() -> MemoryContextPack:
    return MemoryContextPack(user_id="u1")
