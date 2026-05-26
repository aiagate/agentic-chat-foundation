"""Tests for Discord reply sender helpers."""

from unittest.mock import AsyncMock, call

import pytest

from app.presentation.bot.discord_reply_sender import send_discord_reply


@pytest.mark.anyio
async def test_send_discord_reply_uses_cached_channel() -> None:
    """Test sending a Discord reply through a cached channel."""

    class ChannelStub:
        def __init__(self) -> None:
            self.send: AsyncMock = AsyncMock(return_value=None)

    class BotStub:
        def __init__(self, channel: ChannelStub) -> None:
            self._channel = channel

        def get_channel(self, channel_id: int) -> ChannelStub | None:
            return self._channel

    channel = ChannelStub()
    bot = BotStub(channel)

    await send_discord_reply(
        bot,
        {
            "channel_id": "123",
            "contents": ["hello", "world"],
        },
    )

    assert channel.send.await_args_list == [call("hello"), call("world")]


@pytest.mark.anyio
async def test_send_discord_reply_falls_back_to_fetch() -> None:
    """Test sending a Discord reply by fetching the channel."""

    class ChannelStub:
        def __init__(self) -> None:
            self.send: AsyncMock = AsyncMock(return_value=None)

    class BotStub:
        def __init__(self, channel: ChannelStub) -> None:
            self._channel = channel
            self.fetch_channel = AsyncMock(return_value=channel)

        def get_channel(self, channel_id: int) -> ChannelStub | None:
            return None

    channel = ChannelStub()
    bot = BotStub(channel)

    await send_discord_reply(
        bot,
        {
            "channel_id": "123",
            "content": "hello",
        },
    )

    bot.fetch_channel.assert_awaited_once_with(123)
    channel.send.assert_awaited_once_with("hello")
