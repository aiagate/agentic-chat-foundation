"""Tests for transactional generated-reply persistence."""

from typing import Any

import pytest
from flow_res import Err, Ok, is_err

from app.contracts.messages.agentic import AgentEnvelope
from app.contracts.ports.agent_reply_writer import AgentReplyWriteRequest
from app.contracts.ports.unit_of_work import IUnitOfWork
from app.domain.repositories.interfaces import RepositoryError, RepositoryErrorType
from app.domain.value_objects.chat_type import ChatType
from app.infrastructure.services.agent_reply_writer import (
    TransactionalAgentReplyWriter,
)


def _request() -> AgentReplyWriteRequest:
    return AgentReplyWriteRequest(
        chat_type=ChatType.DISCORD,
        guild_id="guild-1",
        channel_id="channel-1",
        user_id="user-1",
        contents=["hello"],
        agent_context=AgentEnvelope(character_id="character-1"),
    )


@pytest.mark.anyio
async def test_writer_returns_error_when_repository_add_fails(mocker: Any) -> None:
    uow = mocker.MagicMock(spec=IUnitOfWork)
    uow.__aenter__ = mocker.AsyncMock(return_value=uow)
    uow.__aexit__ = mocker.AsyncMock(return_value=None)
    repository = mocker.Mock()
    repository.add = mocker.AsyncMock(
        return_value=Err(
            RepositoryError(
                type=RepositoryErrorType.UNEXPECTED,
                message="write failed",
            )
        )
    )
    uow.GetChatRecordRepository.return_value = repository

    result = await TransactionalAgentReplyWriter(uow).write(_request())

    assert is_err(result)
    assert result.error.message == "Failed to save generated content"
    uow.enqueue_event.assert_not_called()
    uow.commit.assert_not_awaited()


@pytest.mark.anyio
async def test_writer_returns_error_when_atomic_commit_fails(mocker: Any) -> None:
    uow = mocker.MagicMock(spec=IUnitOfWork)
    uow.__aenter__ = mocker.AsyncMock(return_value=uow)
    uow.__aexit__ = mocker.AsyncMock(return_value=None)
    repository = mocker.Mock()
    repository.add = mocker.AsyncMock(return_value=Ok(mocker.Mock()))
    uow.GetChatRecordRepository.return_value = repository
    uow.commit = mocker.AsyncMock(
        return_value=Err(
            RepositoryError(
                type=RepositoryErrorType.UNEXPECTED,
                message="commit failed",
            )
        )
    )

    result = await TransactionalAgentReplyWriter(uow).write(_request())

    assert is_err(result)
    assert result.error.message == "Failed to persist generated content"
    uow.enqueue_event.assert_called_once()

