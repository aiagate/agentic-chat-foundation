"""Tests for canonical User identity resolution."""

import pytest
from flow_res import is_ok
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.aggregates.user import UserChannelIdentity
from app.infrastructure.orm_models import UserChannelIdentityORM, UserORM
from app.infrastructure.queries.user_identity_query import SQLAlchemyUserIdentityQuery

USER_ID = "01J00000000000000000000000"


@pytest.mark.anyio
async def test_discord_and_line_identities_resolve_to_same_user(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        session.add(UserORM(id=USER_ID))
        session.add_all(
            [
                UserChannelIdentityORM(
                    user_id=USER_ID,
                    channel="discord",
                    external_participant_id="discord-123",
                ),
                UserChannelIdentityORM(
                    user_id=USER_ID,
                    channel="line",
                    external_participant_id="line-456",
                ),
            ]
        )
        await session.commit()

    query = SQLAlchemyUserIdentityQuery(session_factory)
    discord_result = await query.find_user(
        UserChannelIdentity("discord", "discord-123")
    )
    line_result = await query.find_user(UserChannelIdentity("line", "line-456"))

    assert is_ok(discord_result)
    assert is_ok(line_result)
    assert discord_result.value is not None
    assert line_result.value is not None
    assert discord_result.value.id == line_result.value.id == USER_ID
    assert set(discord_result.value.identities) == set(line_result.value.identities)


@pytest.mark.anyio
async def test_unregistered_identity_resolves_to_none(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    result = await SQLAlchemyUserIdentityQuery(session_factory).find_user(
        UserChannelIdentity("discord", "unknown")
    )

    assert is_ok(result)
    assert result.value is None
