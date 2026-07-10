"""Tests for the observed Mediator wrapper."""

# pyright: reportUnusedFunction=false

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from flow_med import Mediator, Request
from flow_res import Err, Ok, Result, is_err

from app.contracts.messages.app_error import APP_ERROR_DETECTED_TOPIC
from app.contracts.messages.use_case_error import ErrorType, UseCaseError
from app.infrastructure import mediator_observer


@dataclass
class SampleQuery(Request[Result[str, UseCaseError]]):
    """Minimal request object for observer tests."""

    chat_id: str = "chat-1"
    user_id: str = "u1"
    prompt: str = "hello"


@pytest.fixture(autouse=True)
def _reset_observer() -> Generator[None]:
    mediator_observer.reset()
    yield
    mediator_observer.reset()


@pytest.mark.anyio
async def test_observer_publishes_error_event_on_result_error(
    mocker: Any,
) -> None:
    """Test that Result errors are published as application errors."""

    event_bus = mocker.Mock()
    event_bus.publish = AsyncMock(return_value=None)
    mocker.patch.object(
        Mediator,
        "send_async",
        AsyncMock(return_value=Err(UseCaseError(ErrorType.VALIDATION_ERROR, "bad"))),
    )

    mediator_observer.install(event_bus)

    result = await Mediator.send_async(SampleQuery())

    assert is_err(result)
    assert result.error.message == "bad"
    event_bus.publish.assert_awaited_once()
    topic, payload = cast(Any, event_bus.publish.await_args).args
    assert topic == APP_ERROR_DETECTED_TOPIC
    assert payload["operation"] == "SampleQuery"
    assert payload["status"] == "error"
    assert payload["error_code"] == "validation_error"
    assert payload["message"] == "bad"
    assert payload["chat_id"] == "chat-1"
    assert payload["user_id"] == "u1"


@pytest.mark.anyio
async def test_observer_preserves_awaitable_result_chaining(
    mocker: Any,
) -> None:
    """Test that observing Mediator calls does not break .map().unwrap() chains."""

    event_bus = mocker.Mock()
    event_bus.publish = AsyncMock(return_value=None)
    send_async = AsyncMock(return_value=Ok("ok"))
    mocker.patch.object(Mediator, "send_async", send_async)

    mediator_observer.install(event_bus)

    value = await Mediator.send_async(SampleQuery()).map(str.upper).unwrap()

    assert value == "OK"
    send_async.assert_awaited_once()
    event_bus.publish.assert_not_awaited()


@pytest.mark.anyio
async def test_observer_publishes_error_event_on_exception(
    mocker: Any,
) -> None:
    """Test that exceptions are published as application errors."""

    event_bus = mocker.Mock()
    event_bus.publish = AsyncMock(return_value=None)
    mocker.patch.object(
        Mediator,
        "send_async",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    mediator_observer.install(event_bus)

    with pytest.raises(RuntimeError, match="boom"):
        await Mediator.send_async(SampleQuery())

    event_bus.publish.assert_awaited_once()
    topic, payload = cast(Any, event_bus.publish.await_args).args
    assert topic == APP_ERROR_DETECTED_TOPIC
    assert payload["operation"] == "SampleQuery"
    assert payload["status"] == "exception"
    assert payload["error_type"] == "RuntimeError"
    assert payload["message"] == "boom"
