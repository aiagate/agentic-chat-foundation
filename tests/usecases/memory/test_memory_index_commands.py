"""Tests for memory index rebuild and repair use cases."""

from typing import Any, cast

import pytest
from flow_res import Err, Ok, is_err

from app.contracts.ports.memory_index import IMemoryIndex
from app.infrastructure.services.memory_index import (
    MemoryIndexDocument,
    MemorySearchFilters,
    MemorySearchResult,
)
from app.infrastructure.services.memory_store import StoredMemoryDocument
from app.usecases.memory.rebuild_memory_index import (
    RebuildMemoryIndexCommand,
    RebuildMemoryIndexHandler,
)
from app.usecases.memory.repair_memory_index import (
    RepairMemoryIndexCommand,
    RepairMemoryIndexHandler,
)

MemoryIndexPort = IMemoryIndex[
    StoredMemoryDocument,
    MemoryIndexDocument,
    MemorySearchResult,
    MemorySearchFilters,
]


@pytest.fixture
def mock_memory_index(mocker: Any) -> MemoryIndexPort:
    """Return a mocked memory index port."""
    index = mocker.Mock(spec=MemoryIndexPort)
    index.rebuild_memory_index = mocker.Mock(return_value=Ok(3))
    index.repair_memory_index = mocker.Mock(return_value=Ok(2))
    return index


@pytest.mark.anyio
async def test_rebuild_memory_index_success(
    mock_memory_index: MemoryIndexPort,
) -> None:
    """The rebuild handler should call the port and return the count."""
    handler = RebuildMemoryIndexHandler(mock_memory_index)

    result = await handler.handle(RebuildMemoryIndexCommand(user_id="u1"))

    assert not is_err(result)
    assert result.value.indexed_count == 3
    rebuild_stub = cast(Any, mock_memory_index.rebuild_memory_index)
    rebuild_stub.assert_called_once_with(user_id="u1")


@pytest.mark.anyio
async def test_rebuild_memory_index_failure(mocker: Any) -> None:
    """Port errors should be mapped to a use case error."""
    index = mocker.Mock(spec=MemoryIndexPort)
    index.rebuild_memory_index = mocker.Mock(
        return_value=Err(Exception("memory index error"))
    )
    handler = RebuildMemoryIndexHandler(index)

    result = await handler.handle(RebuildMemoryIndexCommand(user_id="u1"))

    assert is_err(result)
    index.rebuild_memory_index.assert_called_once_with(user_id="u1")


@pytest.mark.anyio
async def test_repair_memory_index_success(
    mock_memory_index: MemoryIndexPort,
) -> None:
    """The repair handler should call the port and return the count."""
    handler = RepairMemoryIndexHandler(mock_memory_index)

    result = await handler.handle(RepairMemoryIndexCommand(user_id="u1"))

    assert not is_err(result)
    assert result.value.repaired_count == 2
    repair_stub = cast(Any, mock_memory_index.repair_memory_index)
    repair_stub.assert_called_once_with(user_id="u1")


@pytest.mark.anyio
async def test_repair_memory_index_failure(mocker: Any) -> None:
    """Port errors should be mapped to a use case error."""
    index = mocker.Mock(spec=MemoryIndexPort)
    index.repair_memory_index = mocker.Mock(
        return_value=Err(Exception("memory index error"))
    )
    handler = RepairMemoryIndexHandler(index)

    result = await handler.handle(RepairMemoryIndexCommand(user_id="u1"))

    assert is_err(result)
    index.repair_memory_index.assert_called_once_with(user_id="u1")
