"""Publish the canonical request for one agent inference turn."""

from __future__ import annotations

from dataclasses import dataclass

from flow_med import Request, RequestHandler
from flow_res import Ok, Result
from injector import inject

from app.contracts.messages.agentic import AgentEnvelope, with_character_id
from app.contracts.messages.chat_events import (
    CHAT_AGENT_TURN_REQUESTED_TOPIC,
    build_agent_turn_requested_payload,
)
from app.contracts.messages.use_case_error import UseCaseError
from app.contracts.ports.event_bus import IEventBus
from app.domain.value_objects.chat_type import ChatType


@dataclass
class RequestAgentTurnCommand(Request[Result[None, UseCaseError]]):
    """Request inference through the shared event route."""

    chat_id: str
    user_id: str
    chat_type: ChatType
    guild_id: str
    channel_id: str
    character_id: str
    source_request_id: str | None = None
    tool_failure_context: str | None = None
    agent_context: AgentEnvelope | None = None


class RequestAgentTurnHandler(
    RequestHandler[RequestAgentTurnCommand, Result[None, UseCaseError]]
):
    """Publish the canonical agent-turn request event."""

    @inject
    def __init__(self, event_bus: IEventBus) -> None:
        self._event_bus = event_bus

    async def handle(
        self,
        request: RequestAgentTurnCommand,
    ) -> Result[None, UseCaseError]:
        await self._event_bus.publish(
            CHAT_AGENT_TURN_REQUESTED_TOPIC,
            build_agent_turn_requested_payload(
                chat_id=request.chat_id,
                user_id=request.user_id,
                chat_type=request.chat_type.to_primitive(),
                guild_id=request.guild_id,
                channel_id=request.channel_id,
                source_request_id=request.source_request_id,
                tool_failure_context=request.tool_failure_context,
                agent_envelope=with_character_id(
                    request.agent_context,
                    request.character_id,
                ),
            ),
        )
        return Ok(None)
