"""Worker handler for canonical agent-turn requests."""

from __future__ import annotations

import logging
from collections.abc import Mapping

from flow_med import Mediator

from app.contracts.messages.chat_events import CHAT_AGENT_TURN_REQUESTED_TOPIC
from app.presentation.worker.event_payloads import (
    AgentTurnRequestedPayload,
    extract_agent_envelope,
    parse_worker_event_payload,
)
from app.presentation.worker.registry import event_handler
from app.usecases.agent.run_agent_turn import RunAgentTurnQuery

logger = logging.getLogger(__name__)


@event_handler(CHAT_AGENT_TURN_REQUESTED_TOPIC)
async def on_agent_turn_requested(payload: Mapping[str, object]) -> None:
    """Run inference for one normalized agent-turn request."""
    event = parse_worker_event_payload(
        AgentTurnRequestedPayload,
        payload,
        event_name="Agent turn requested",
    )
    if event is None or event.character_id is None:
        logger.warning("Agent turn request missing character_id: %s", payload)
        return
    await Mediator.send_async(
        RunAgentTurnQuery(
            chat_id=event.chat_id,
            user_id=event.user_id,
            chat_type=event.chat_type,
            guild_id=event.guild_id,
            channel_id=event.channel_id,
            character_id=event.character_id,
            source_request_id=event.source_request_id,
            tool_call_id=event.tool_call_id,
            tool_failure_context=event.tool_failure_context,
            agent_context=extract_agent_envelope(event),
        )
    )
