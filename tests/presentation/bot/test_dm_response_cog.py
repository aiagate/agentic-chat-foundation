"""Tests for the Discord DM response cog."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock

import pytest
from flow_res import Ok

from app.presentation.bot.cogs.dm_response_cog import DirectMessageResponseCog
from app.usecases.conversation.accept_incoming_message import (
    AcceptIncomingMessageCommand,
)


@dataclass
class _FakeAuthor:
    id: int


class _FakeDMChannel:
    def __init__(self, channel_id: int) -> None:
        self.id = channel_id
        self.send = AsyncMock(return_value=None)


@dataclass
class _FakeMessage:
    author: _FakeAuthor
    channel: _FakeDMChannel
    content: str | None
    id: int = 789


class _FakeBot:
    def __init__(self, user: object) -> None:
        self.user = user


@pytest.mark.anyio
async def test_dm_response_cog_saves_text_message(
    mocker: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-empty DM should be forwarded to the save use case."""

    send_async = AsyncMock(return_value=Ok(None))
    mocker.patch(
        "app.presentation.bot.cogs.dm_response_cog.Mediator.send_async", send_async
    )
    monkeypatch.setattr(
        "app.presentation.bot.cogs.dm_response_cog.discord.DMChannel",
        _FakeDMChannel,
    )

    bot_user = object()
    bot = _FakeBot(user=bot_user)
    cog = DirectMessageResponseCog(bot)  # type: ignore[arg-type]
    message = _FakeMessage(
        author=_FakeAuthor(id=123),
        channel=_FakeDMChannel(channel_id=456),
        content="  hello world  ",
    )

    await cog.on_message(message)  # type: ignore[arg-type]

    send_async.assert_awaited_once()
    await_args = send_async.await_args
    assert await_args is not None
    request = await_args.args[0]
    assert isinstance(request, AcceptIncomingMessageCommand)
    assert request.message.external_participant_id == "123"
    assert request.message.external_conversation_id == "456"
    assert request.message.metadata == {"guild_id": "DM", "channel_id": "456"}
    assert request.message.text == "hello world"


@pytest.mark.anyio
async def test_dm_response_cog_skips_blank_text_message(
    mocker: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Blank DM content should not enter the save flow."""

    send_async = AsyncMock(return_value=Ok(None))
    mocker.patch(
        "app.presentation.bot.cogs.dm_response_cog.Mediator.send_async", send_async
    )
    monkeypatch.setattr(
        "app.presentation.bot.cogs.dm_response_cog.discord.DMChannel",
        _FakeDMChannel,
    )

    bot_user = object()
    bot = _FakeBot(user=bot_user)
    cog = DirectMessageResponseCog(bot)  # type: ignore[arg-type]
    message = _FakeMessage(
        author=_FakeAuthor(id=123),
        channel=_FakeDMChannel(channel_id=456),
        content="   ",
    )

    await cog.on_message(message)  # type: ignore[arg-type]

    send_async.assert_not_awaited()
    message.channel.send.assert_not_awaited()
