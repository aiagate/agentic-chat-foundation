"""Tests for raw chat log query."""

from datetime import UTC, datetime

import pytest
from flow_res import is_ok
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts.messages.chat_type import ChatType
from app.contracts.ports.unit_of_work import IUnitOfWork
from app.infrastructure.orm_models import (
    ChatORM,
    UserChannelIdentityORM,
    UserORM,
)


async def _seed_raw_chat_logs(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Insert chat rows for raw log query tests."""
    async with session_factory() as session:
        session.add_all(
            [
                UserORM(id="u1"),
                UserORM(id="u2"),
                UserChannelIdentityORM(
                    user_id="u1",
                    channel="discord",
                    external_participant_id="u1",
                ),
                UserChannelIdentityORM(
                    user_id="u1",
                    channel="line",
                    external_participant_id="u1",
                ),
                UserChannelIdentityORM(
                    user_id="u2",
                    channel="discord",
                    external_participant_id="u2",
                ),
                ChatORM(
                    id="01J0RAWCHAT000000000000001",
                    channel="discord",
                    external_conversation_id="channel-1",
                    external_participant_id="discord-user-1",
                    user_id="u1",
                    accepted_sequence=1,
                    role="user",
                    message_content={
                        "type": "TEXT",
                        "payload": {"texts": ["first"]},
                    },
                    created_at=datetime(2026, 5, 20, 8, 0, tzinfo=UTC),
                    updated_at=datetime(2026, 5, 20, 8, 0, tzinfo=UTC),
                    channel_metadata={"guild_id": "guild-1", "channel_id": "channel-1"},
                ),
                ChatORM(
                    id="01J0RAWCHAT000000000000002",
                    channel="discord",
                    external_conversation_id="channel-1",
                    external_participant_id="discord-user-1",
                    user_id="u1",
                    accepted_sequence=2,
                    role="assistant",
                    message_content={
                        "type": "TEXT",
                        "payload": {"texts": ["second"]},
                    },
                    created_at=datetime(2026, 5, 20, 9, 0, tzinfo=UTC),
                    updated_at=datetime(2026, 5, 20, 9, 0, tzinfo=UTC),
                    channel_metadata={"guild_id": "guild-1", "channel_id": "channel-1"},
                ),
                ChatORM(
                    id="01J0RAWCHAT000000000000003",
                    channel="line",
                    external_conversation_id="line-user-1",
                    external_participant_id="line-user-1",
                    user_id="u1",
                    accepted_sequence=3,
                    role="user",
                    message_content={
                        "type": "TEXT",
                        "payload": {"texts": ["ignored"]},
                    },
                    created_at=datetime(2026, 5, 20, 10, 0, tzinfo=UTC),
                    updated_at=datetime(2026, 5, 20, 10, 0, tzinfo=UTC),
                    channel_metadata={},
                ),
                ChatORM(
                    id="01J0RAWCHAT000000000000004",
                    channel="discord",
                    external_conversation_id="channel-2",
                    external_participant_id="discord-user-2",
                    user_id="u2",
                    accepted_sequence=4,
                    role="user",
                    message_content={
                        "type": "TEXT",
                        "payload": {"texts": ["other"]},
                    },
                    created_at=datetime(2026, 5, 20, 11, 0, tzinfo=UTC),
                    updated_at=datetime(2026, 5, 20, 11, 0, tzinfo=UTC),
                    channel_metadata={"guild_id": "guild-2", "channel_id": "channel-2"},
                ),
            ]
        )
        await session.commit()


@pytest.mark.anyio
async def test_raw_chat_log_query_returns_chronological_messages(
    uow: IUnitOfWork,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Test raw chat log query ordering and filtering."""
    await _seed_raw_chat_logs(session_factory)

    async with uow:
        query = uow.GetRawChatLogQuery()
        result = await query.get_pending_memory_source_items(
            "shirasagi-reina",
            "u1",
            ChatType.DISCORD,
            since=datetime(2026, 5, 20, 8, 30, tzinfo=UTC),
            until=datetime(2026, 5, 20, 9, 30, tzinfo=UTC),
            limit=10,
        )
        assert is_ok(result)
        logs = result.value

        assert len(logs) == 1
        assert logs[0].user_id == "u1"
        assert logs[0].role == "assistant"
        assert logs[0].message_content["payload"]["texts"] == ["second"]


@pytest.mark.anyio
async def test_raw_chat_log_query_lists_distinct_user_ids(
    uow: IUnitOfWork,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Test raw chat log user ID lookup."""

    await _seed_raw_chat_logs(session_factory)

    async with uow:
        query = uow.GetRawChatLogQuery()
        result = await query.list_pending_memory_user_ids(
            "shirasagi-reina",
            since=datetime(2026, 5, 20, 8, 0, tzinfo=UTC),
            until=datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
            limit=10,
        )
        assert is_ok(result)
        user_ids = result.value

        assert user_ids == ["u1", "u2"]


@pytest.mark.anyio
async def test_raw_chat_log_query_excludes_consolidated_sources(
    uow: IUnitOfWork,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Long-term memory organization must not select processed chat rows."""

    await _seed_raw_chat_logs(session_factory)
    async with uow:
        mark_result = await (
            uow.GetMemoryConsolidatedChatSourceRepository().mark_consolidated(
                ["01J0RAWCHAT000000000000001"],
                consolidated_at=datetime(2026, 5, 21, 3, 0, tzinfo=UTC),
            )
        )
        assert is_ok(mark_result)
        await uow.commit()

    async with uow:
        result = await uow.GetRawChatLogQuery().get_pending_memory_source_items(
            "shirasagi-reina",
            "u1",
            ChatType.DISCORD,
            limit=10,
        )

    assert is_ok(result)
    assert [item.id for item in result.value] == ["01J0RAWCHAT000000000000002"]
