"""Scheduled transactional outbox dispatch."""

from flow_med import Mediator

from app.presentation.worker.registry import scheduled_task
from app.usecases.messaging.dispatch_outbox_messages import (
    DispatchOutboxMessagesCommand,
)

OUTBOX_DISPATCH_INTERVAL_SECONDS = 1


@scheduled_task(interval_seconds=OUTBOX_DISPATCH_INTERVAL_SECONDS)
async def dispatch_outbox_messages() -> None:
    """Publish one pending outbox batch."""
    await Mediator.send_async(DispatchOutboxMessagesCommand())
