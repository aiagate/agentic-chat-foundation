"""Tests for Discord discussion event normalization."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.contracts.messages.discussion import DiscussionAuthorKind
from app.presentation.bot.cogs.discussion_cog import (
    DiscordDiscussionCog,
    DiscussionCogSettings,
)


@dataclass
class _User:
    id: int
    name: str
    display_name: str
    bot: bool


@dataclass
class _ObjectWithId:
    id: int


@dataclass
class _Message:
    id: int
    author: _User
    content: str
    guild: _ObjectWithId | None
    channel: _ObjectWithId
    webhook_id: int | None = None
    mentions: list[_User] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class _Bot:
    def __init__(self, user: _User) -> None:
        self.user = user


def _cog() -> tuple[DiscordDiscussionCog, _User]:
    self_user = _User(1, "self", "Self", True)
    cog = DiscordDiscussionCog(
        _Bot(self_user),  # type: ignore[arg-type]
        DiscussionCogSettings(channel_ids=frozenset({10}), character_id="agent-1"),
    )
    return cog, self_user


def test_discussion_cog_accepts_every_other_bot_account() -> None:
    cog, self_user = _cog()
    message = _Message(
        id=100,
        author=_User(2, "other", "Other Bot", True),
        content=" hello ",
        guild=_ObjectWithId(20),
        channel=_ObjectWithId(10),
        mentions=[self_user],
    )

    incoming = cog._incoming(message, recovered=False)  # type: ignore[arg-type]

    assert incoming is not None
    assert incoming.author_kind is DiscussionAuthorKind.BOT
    assert incoming.text == "hello"
    assert incoming.mentioned_self is True


def test_discussion_cog_ignores_live_self_and_recovers_historical_self() -> None:
    cog, self_user = _cog()
    message = _Message(
        id=100,
        author=self_user,
        content="my previous message",
        guild=_ObjectWithId(20),
        channel=_ObjectWithId(10),
    )

    assert cog._incoming(message, recovered=False) is None  # type: ignore[arg-type]
    recovered = cog._incoming(message, recovered=True)  # type: ignore[arg-type]

    assert recovered is not None
    assert recovered.author_kind is DiscussionAuthorKind.SELF
    assert recovered.recovered is True


def test_discussion_cog_ignores_webhook_messages() -> None:
    cog, _ = _cog()
    message = _Message(
        id=100,
        author=_User(2, "hook", "Webhook", True),
        content="automated feed",
        guild=_ObjectWithId(20),
        channel=_ObjectWithId(10),
        webhook_id=30,
    )

    assert cog._incoming(message, recovered=False) is None  # type: ignore[arg-type]


def test_discussion_cog_uses_character_delay_and_speeds_up_mentions() -> None:
    self_user = _User(1, "self", "Self", True)
    cog = DiscordDiscussionCog(
        _Bot(self_user),  # type: ignore[arg-type]
        DiscussionCogSettings(
            channel_ids=frozenset({10}),
            character_id="agent-1",
            response_delay_min_seconds=4,
            response_delay_max_seconds=4,
        ),
    )
    message = _Message(
        id=100,
        author=_User(2, "human", "Human", False),
        content="hello",
        guild=_ObjectWithId(20),
        channel=_ObjectWithId(10),
    )
    incoming = cog._incoming(message, recovered=False)  # type: ignore[arg-type]
    assert incoming is not None

    assert cog._response_delay(incoming) == 4
    assert (
        cog._response_delay(incoming.model_copy(update={"mentioned_self": True})) == 1
    )
    assert cog._response_delay(incoming.model_copy(update={"recovered": True})) == 0
