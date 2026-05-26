"""Tests for bot entrypoint helpers."""

from unittest.mock import AsyncMock, Mock

import pytest

from app.contracts.ports.event_bus import IEventBus


@pytest.mark.anyio
async def test_bot_setup_hook_initializes_event_bus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that the bot entrypoint wires the event bus."""
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./bot.db")

    from app.presentation.bot import __main__ as bot_main

    event_bus = AsyncMock(spec=IEventBus)
    event_bus.subscribe = AsyncMock(return_value=None)
    event_bus.start = AsyncMock(return_value=None)

    class InjectorStub:
        def __init__(self) -> None:
            self.modules = None

        def __call__(self, modules: list[object]) -> "InjectorStub":
            self.modules = modules
            return self

        def get(self, interface: object) -> IEventBus:
            return event_bus

    injector_stub = InjectorStub()
    initialize_stub = Mock(return_value=None)
    monkeypatch.setattr(bot_main, "Injector", injector_stub)
    monkeypatch.setattr(bot_main.Mediator, "initialize", initialize_stub)
    monkeypatch.setattr(bot_main, "init_db", Mock(return_value=None))

    bot = bot_main.MyBot()
    bot.add_cog = AsyncMock(return_value=None)  # type: ignore[method-assign]

    await bot.setup_hook()

    initialize_stub.assert_called_once_with(injector_stub)
    assert bot.injector is injector_stub
    event_bus.subscribe.assert_awaited_once()
    event_bus.start.assert_awaited_once()
