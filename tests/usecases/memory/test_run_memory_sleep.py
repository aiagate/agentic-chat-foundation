"""Tests for the memory sleep use case."""

from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from flow_res import is_err

from app.contracts.ports.memory_consolidation import IMemoryConsolidationService
from app.contracts.ports.memory_store import IMemoryStore
from app.domain.repositories import IUnitOfWork
from app.usecases.memory.run_memory_sleep import (
    RunMemorySleepCommand,
    RunMemorySleepHandler,
)


@pytest.mark.anyio
async def test_run_memory_sleep_handler_invokes_consolidation_service(
    mocker: Any,
) -> None:
    """Test that the sleep command delegates to the consolidation port."""

    memory_store = mocker.Mock(spec=IMemoryStore)
    uow = mocker.Mock(spec=IUnitOfWork)
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    raw_chat_log_query = mocker.Mock()
    uow.GetRawChatLogQuery = mocker.Mock(return_value=raw_chat_log_query)
    consolidation_service = mocker.Mock(spec=IMemoryConsolidationService)
    consolidation_service.run_memory_sleep = AsyncMock(return_value=2)

    handler = RunMemorySleepHandler(memory_store, uow, consolidation_service)

    result = await handler.handle(RunMemorySleepCommand())

    assert not is_err(result)
    assert result.value.consolidated_count == 2
    assert uow.GetRawChatLogQuery.call_count == 1
    consolidation_stub = cast(Any, consolidation_service.run_memory_sleep)
    consolidation_stub.assert_awaited_once()
    await_args = consolidation_stub.await_args
    assert await_args is not None
    assert await_args.args == (memory_store,)
    assert await_args.kwargs["raw_chat_log_query"] is raw_chat_log_query


@pytest.mark.anyio
async def test_run_memory_sleep_handler_reports_failures(
    mocker: Any,
) -> None:
    """Test that consolidation failures are surfaced as use case errors."""

    memory_store = mocker.Mock(spec=IMemoryStore)
    uow = mocker.Mock(spec=IUnitOfWork)
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    uow.GetRawChatLogQuery = mocker.Mock(return_value=mocker.Mock())
    consolidation_service = mocker.Mock(spec=IMemoryConsolidationService)
    consolidation_service.run_memory_sleep = AsyncMock(side_effect=RuntimeError("boom"))

    handler = RunMemorySleepHandler(memory_store, uow, consolidation_service)

    result = await handler.handle(RunMemorySleepCommand())

    assert is_err(result)
    assert uow.GetRawChatLogQuery.call_count == 1


@pytest.mark.anyio
async def test_run_memory_sleep_handler_does_not_use_run_repository(
    mocker: Any,
) -> None:
    """Test that the handler no longer depends on a run repository."""

    memory_store = mocker.Mock(spec=IMemoryStore)
    uow = mocker.Mock(spec=IUnitOfWork)
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    uow.GetRawChatLogQuery = mocker.Mock(return_value=mocker.Mock())
    consolidation_service = mocker.Mock(spec=IMemoryConsolidationService)
    consolidation_service.run_memory_sleep = AsyncMock(return_value=0)

    handler = RunMemorySleepHandler(memory_store, uow, consolidation_service)

    result = await handler.handle(RunMemorySleepCommand())

    assert not is_err(result)
    assert result.value.consolidated_count == 0
    consolidation_service.run_memory_sleep.assert_awaited_once()
