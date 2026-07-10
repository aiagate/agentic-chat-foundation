"""Tests for transactional outbox dispatch."""

from datetime import UTC, datetime
from typing import Any

import pytest
from flow_res import Ok, is_err

from app.contracts.messages.outbox_message import OutboxMessage
from app.contracts.ports.event_bus import IEventBus
from app.contracts.ports.outbox_store import IOutboxStore
from app.usecases.messaging.dispatch_outbox_messages import (
    DispatchOutboxMessagesCommand,
    DispatchOutboxMessagesHandler,
)


@pytest.mark.anyio
async def test_dispatch_outbox_marks_published(mocker: Any) -> None:
    now = datetime(2026, 6, 28, tzinfo=UTC)
    message = OutboxMessage(
        id="event-1",
        topic="example.created",
        payload={"event_id": "event-1"},
        created_at=now,
        attempt_count=1,
        claim_token="claim-1",
    )
    store = mocker.Mock(spec=IOutboxStore)
    store.claim_pending = mocker.AsyncMock(return_value=Ok([message]))
    store.mark_published = mocker.AsyncMock(return_value=Ok(None))
    event_bus = mocker.Mock(spec=IEventBus)
    event_bus.publish = mocker.AsyncMock(return_value=None)

    result = await DispatchOutboxMessagesHandler(store, event_bus).handle(
        DispatchOutboxMessagesCommand(reference_time=now)
    )

    assert not is_err(result)
    assert result.value.published_count == 1
    event_bus.publish.assert_awaited_once_with(message.topic, message.payload)
    store.mark_published.assert_awaited_once_with(
        message.id,
        message.claim_token,
        published_at=now,
    )


@pytest.mark.anyio
async def test_dispatch_outbox_schedules_retry_after_publish_failure(
    mocker: Any,
) -> None:
    now = datetime(2026, 6, 28, tzinfo=UTC)
    message = OutboxMessage(
        id="event-1",
        topic="example.created",
        payload={"event_id": "event-1"},
        created_at=now,
        attempt_count=1,
        claim_token="claim-1",
    )
    store = mocker.Mock(spec=IOutboxStore)
    store.claim_pending = mocker.AsyncMock(return_value=Ok([message]))
    store.mark_failed = mocker.AsyncMock(return_value=Ok(None))
    event_bus = mocker.Mock(spec=IEventBus)
    event_bus.publish = mocker.AsyncMock(side_effect=RuntimeError("offline"))

    result = await DispatchOutboxMessagesHandler(store, event_bus).handle(
        DispatchOutboxMessagesCommand(reference_time=now)
    )

    assert not is_err(result)
    assert result.value.failed_count == 1
    failed_call = store.mark_failed.await_args
    assert failed_call.args == (message.id, message.claim_token)
    assert failed_call.kwargs["error"] == "offline"
    assert failed_call.kwargs["next_attempt_at"] > now
