"""Worker handler for durable AgentRun wakeups."""

from __future__ import annotations

import logging
from collections.abc import Mapping

from flow_med import Mediator

from app.contracts.messages.agent_run_events import AGENT_RUN_WAKEUP_TOPIC
from app.presentation.worker.event_payloads import (
    AgentRunWakeupPayload,
    parse_worker_event_payload,
)
from app.presentation.worker.registry import event_handler
from app.usecases.agent.advance_agent_run import AdvanceAgentRunCommand

logger = logging.getLogger(__name__)


@event_handler(AGENT_RUN_WAKEUP_TOPIC)
async def on_agent_run_wakeup(payload: Mapping[str, object]) -> None:
    """Advance durable state; duplicate and stale wakeups become no-ops."""
    event = parse_worker_event_payload(
        AgentRunWakeupPayload,
        payload,
        event_name="AgentRun wakeup",
    )
    if event is None:
        return
    await Mediator.send_async(
        AdvanceAgentRunCommand(
            agent_run_id=event.agent_run_id,
            wake_sequence=event.wake_sequence,
        )
    )
