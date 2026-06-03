"""Worker handlers for saved chat events."""

import logging
from collections.abc import Mapping

from flow_med import Mediator

from app.contracts.messages.chat_events import (
    DISCORD_CHAT_SAVED_TOPIC,
    LINE_CHAT_SAVED_TOPIC,
)
from app.domain.value_objects.chat_type import ChatType
from app.presentation.worker.event_payloads import (
    DiscordChatSavedPayload,
    LineChatSavedPayload,
    extract_agent_envelope,
    parse_worker_event_payload,
)
from app.presentation.worker.registry import event_handler
from app.usecases.agent.run_agent_turn import RunAgentTurnQuery

logger = logging.getLogger(__name__)


@event_handler(DISCORD_CHAT_SAVED_TOPIC)
async def on_discord_chat_saved(payload: Mapping[str, object]) -> None:
    """Handle a saved Discord chat message."""

    event = parse_worker_event_payload(
        DiscordChatSavedPayload,
        payload,
        event_name="Discord chat saved",
    )
    if event is None:
        return

    await Mediator.send_async(
        RunAgentTurnQuery(
            chat_id=event.chat_id,
            guild_id=event.guild_id,
            channel_id=event.channel_id,
            user_id=event.user_id,
            chat_type=ChatType.DISCORD,
            character_id=event.character_id,
            agent_context=extract_agent_envelope(event),
        )
    )


@event_handler(LINE_CHAT_SAVED_TOPIC)
async def on_line_chat_saved(payload: Mapping[str, object]) -> None:
    """Handle a saved LINE chat message."""

    event = parse_worker_event_payload(
        LineChatSavedPayload,
        payload,
        event_name="LINE chat saved",
    )
    if event is None:
        return

    await Mediator.send_async(
        RunAgentTurnQuery(
            chat_id=event.chat_id,
            guild_id="LINE",
            channel_id=event.chat_id,
            user_id=event.user_id,
            chat_type=ChatType.LINE,
            character_id=event.character_id,
            agent_context=extract_agent_envelope(event),
        )
    )
