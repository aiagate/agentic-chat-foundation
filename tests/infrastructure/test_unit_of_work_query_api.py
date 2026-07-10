"""Tests for Unit of Work query API behavior."""

import pytest

from app.contracts.ports.unit_of_work import IUnitOfWork
from app.domain.aggregates.user import User
from app.domain.value_objects import UserId


@pytest.mark.anyio
async def test_uow_query_api_reuses_cached_instances(
    uow: IUnitOfWork,
) -> None:
    """Test that UoW reuses cached repository and query instances."""
    async with uow:
        repo_first = uow.GetRepository(User, UserId)
        repo_second = uow.GetRepository(User, UserId)
        query_first = uow.GetChatHistoryQuery()
        query_second = uow.GetChatHistoryQuery()
        raw_query_first = uow.GetRawChatLogQuery()
        raw_query_second = uow.GetRawChatLogQuery()
        chat_record_repo_first = uow.GetChatRecordRepository()
        chat_record_repo_second = uow.GetChatRecordRepository()
        source_repo_first = uow.GetMemoryConsolidatedChatSourceRepository()
        source_repo_second = uow.GetMemoryConsolidatedChatSourceRepository()

        assert repo_first is repo_second
        assert query_first is query_second
        assert raw_query_first is raw_query_second
        assert chat_record_repo_first is chat_record_repo_second
        assert source_repo_first is source_repo_second


@pytest.mark.anyio
async def test_uow_query_api_requires_active_session(
    uow: IUnitOfWork,
) -> None:
    """Test that query and repository access require an active session."""
    with pytest.raises(RuntimeError):
        uow.GetChatHistoryQuery()

    with pytest.raises(RuntimeError):
        uow.GetRawChatLogQuery()

    with pytest.raises(RuntimeError):
        uow.GetChatRecordRepository()

    with pytest.raises(RuntimeError):
        uow.GetMemoryConsolidatedChatSourceRepository()

    with pytest.raises(RuntimeError):
        uow.GetRepository(User, UserId)

    with pytest.raises(RuntimeError):
        await uow.commit()

    with pytest.raises(RuntimeError):
        await uow.rollback()
