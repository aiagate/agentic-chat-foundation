"""Tests for autonomous Discord discussion delivery."""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import discord
import pytest

from app.presentation.bot.discord_discussion_sender import (
    DiscordDiscussionMessageSender,
)


@pytest.mark.anyio
async def test_sender_delivers_all_texts_and_records_provider_ids() -> None:
    channel = SimpleNamespace(
        send=AsyncMock(
            side_effect=[
                SimpleNamespace(id=1, content="first", created_at=datetime.now(UTC)),
                SimpleNamespace(id=2, content="second", created_at=datetime.now(UTC)),
            ]
        )
    )
    sender = DiscordDiscussionMessageSender(
        cast(discord.abc.Messageable, cast(Any, channel))
    )

    sent = await sender.send(["first", "second"])

    assert [item.external_message_id for item in sent] == ["1", "2"]
    assert [item.text for item in sent] == ["first", "second"]


@pytest.mark.anyio
async def test_sender_splits_text_at_discord_limit() -> None:
    long_text = "x" * 2001
    channel = SimpleNamespace(
        send=AsyncMock(
            side_effect=[
                SimpleNamespace(id=1, content="x" * 2000, created_at=datetime.now(UTC)),
                SimpleNamespace(id=2, content="x", created_at=datetime.now(UTC)),
            ]
        )
    )
    sender = DiscordDiscussionMessageSender(
        cast(discord.abc.Messageable, cast(Any, channel))
    )

    sent = await sender.send([long_text])

    assert [len(item.text) for item in sent] == [2000, 1]
