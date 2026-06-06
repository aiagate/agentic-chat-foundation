"""Tests for chat history query."""

from datetime import UTC, datetime

import pytest
from flow_res import is_ok
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.repositories import IUnitOfWork
from app.domain.value_objects.chat_type import ChatType
from app.infrastructure.orm_models.chat_orm import ChatORM


@pytest.mark.anyio
async def test_get_recent_history_returns_chronological_order(
    uow: IUnitOfWork,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Test recent history order and role preservation."""

    await _seed_chat_rows(session_factory)

    async with uow:
        query = uow.GetChatHistoryQuery()
        result = await query.get_recent_history(
            ChatType.DISCORD,
            user_id="u1",
            guild_id="DM",
            channel_id="123",
            limit=10,
        )
        assert is_ok(result)
        history = result.value

        assert len(history) == 3
        assert [item.role for item in history] == [
            "user",
            "assistant",
            "user",
        ]
        assert [item.content for item in history] == [
            "first",
            "assistant reply\n\nfollow-up",
            "second",
        ]
        assert [item.id for item in history] == [
            "chat-1",
            "chat-2",
            "chat-3",
        ]
        assert history[0].chat_type == ChatType.DISCORD
        assert history[1].user_id == "u1"
        assert history[2].occurred_at == datetime(2026, 5, 18, 10, 10)


@pytest.mark.anyio
async def test_get_recent_history_filters_by_scope(
    uow: IUnitOfWork,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Test that recent history excludes rows from other channels."""

    await _seed_chat_rows(session_factory)
    await _seed_other_scope_rows(session_factory)

    async with uow:
        query = uow.GetChatHistoryQuery()
        result = await query.get_recent_history(
            ChatType.DISCORD,
            user_id="u1",
            guild_id="DM",
            channel_id="123",
            limit=10,
        )

    assert is_ok(result)
    history = result.value
    assert [item.id for item in history] == ["chat-1", "chat-2", "chat-3"]


async def _seed_chat_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        session.add_all(
            [
                ChatORM(
                    id="chat-1",
                    type=ChatType.DISCORD.to_primitive(),
                    user_id="u1",
                    role="user",
                    message_content={
                        "type": "TEXT",
                        "payload": {"text": "first"},
                    },
                    version=0,
                    created_at=datetime(2026, 5, 18, 10, 0, tzinfo=UTC),
                    updated_at=datetime(2026, 5, 18, 10, 0, tzinfo=UTC),
                    discord_guild_id="DM",
                    discord_channel_id="123",
                ),
                ChatORM(
                    id="chat-2",
                    type=ChatType.DISCORD.to_primitive(),
                    user_id="u1",
                    role="assistant",
                    message_content={
                        "type": "TEXT",
                        "payload": {"texts": ["assistant reply", "follow-up"]},
                    },
                    version=0,
                    created_at=datetime(2026, 5, 18, 10, 5, tzinfo=UTC),
                    updated_at=datetime(2026, 5, 18, 10, 5, tzinfo=UTC),
                    discord_guild_id="DM",
                    discord_channel_id="123",
                ),
                ChatORM(
                    id="chat-3",
                    type=ChatType.DISCORD.to_primitive(),
                    user_id="u1",
                    role="user",
                    message_content={
                        "type": "TEXT",
                        "payload": {"text": "second"},
                    },
                    version=0,
                    created_at=datetime(2026, 5, 18, 10, 10, tzinfo=UTC),
                    updated_at=datetime(2026, 5, 18, 10, 10, tzinfo=UTC),
                    discord_guild_id="DM",
                    discord_channel_id="123",
                ),
            ]
        )
        await session.commit()


async def _seed_other_scope_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        session.add(
            ChatORM(
                id="chat-x",
                type=ChatType.DISCORD.to_primitive(),
                user_id="u1",
                role="user",
                message_content={
                    "type": "TEXT",
                    "payload": {"text": "other channel"},
                },
                version=0,
                created_at=datetime(2026, 5, 18, 10, 15, tzinfo=UTC),
                updated_at=datetime(2026, 5, 18, 10, 15, tzinfo=UTC),
                discord_guild_id="DM",
                discord_channel_id="999",
            )
        )
        await session.commit()
