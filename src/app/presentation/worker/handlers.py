"""Event handlers for Worker."""

import logging
from datetime import time
from typing import Any, cast

from flow_med import Mediator
from flow_res import is_err

from app.contracts.messages.chat_events import (
    CHAT_SEARCH_COMPLETED_TOPIC,
    CHAT_SEARCH_REQUESTED_TOPIC,
    DISCORD_CHAT_SAVED_TOPIC,
    LINE_CHAT_SAVED_TOPIC,
)
from app.contracts.messages.tool_use import ToolName
from app.domain.value_objects.chat_type import ChatType
from app.presentation.worker.registry import event_handler, scheduled_task
from app.usecases.chat.generate_content import GenerateContentQuery
from app.usecases.chat.generate_content_with_retrieved_context import (
    GenerateContentWithRetrievedContextQuery,
)
from app.usecases.memory.run_memory_sleep import RunMemorySleepCommand
from app.usecases.search.handle_search_request import HandleSearchRequestCommand
from app.usecases.users.welcome_user import WelcomeUserCommand

logger = logging.getLogger(__name__)

MEMORY_SLEEP_INTERVAL_SECONDS = 2 * 24 * 60 * 60
MEMORY_SLEEP_RUN_TIME = time(hour=3)


@event_handler("user.created")
async def on_user_created(payload: dict[str, Any]) -> None:
    """Handle user.created event."""
    user_id = payload.get("user_id")
    if not user_id:
        return

    # Mediatorを介してUseCaseを実行
    await Mediator.send_async(WelcomeUserCommand(user_id=user_id))


@event_handler(DISCORD_CHAT_SAVED_TOPIC)
async def on_discord_chat_saved(payload: dict[str, Any]) -> None:
    """Handle a saved Discord chat message."""
    await _generate_reply(payload, ChatType.DISCORD)


@event_handler(LINE_CHAT_SAVED_TOPIC)
async def on_line_chat_saved(payload: dict[str, Any]) -> None:
    """Handle a saved LINE chat message."""
    await _generate_reply(payload, ChatType.LINE)


async def _generate_reply(payload: dict[str, Any], chat_type: ChatType) -> None:
    chat_id = payload.get("chat_id")
    content = payload.get("content")

    if not chat_id or not content:
        logger.warning("Chat saved payload missing required fields: %s", payload)
        return

    if chat_type is ChatType.DISCORD:
        guild_id = payload.get("guild_id")
        channel_id = payload.get("channel_id")
        if not guild_id or not channel_id:
            logger.warning("Discord chat payload missing route fields: %s", payload)
            return

        await Mediator.send_async(
            GenerateContentQuery(
                prompt=content,
                chat_id=str(chat_id),
                guild_id=guild_id,
                channel_id=channel_id,
                user_id=str(payload.get("user_id") or chat_id),
                chat_type=ChatType.DISCORD,
            )
        )
        return

    user_id = payload.get("user_id")
    if not user_id:
        logger.warning("LINE chat payload missing user_id: %s", payload)
        return

    await Mediator.send_async(
        GenerateContentQuery(
            prompt=content,
            chat_id=str(chat_id),
            guild_id="LINE",
            channel_id=str(chat_id),
            user_id=user_id,
            chat_type=ChatType.LINE,
        )
    )


@event_handler(CHAT_SEARCH_REQUESTED_TOPIC)
async def on_chat_search_requested(payload: dict[str, Any]) -> None:
    """Handle a requested search."""
    search_session_id = payload.get("search_session_id")
    source_request_id = payload.get("source_request_id")
    chat_id = payload.get("chat_id")
    user_id = payload.get("user_id")
    prompt = payload.get("prompt")
    query = payload.get("query")
    user_message = payload.get("user_message")
    tool_name = payload.get("tool_name")
    if (
        not search_session_id
        or not source_request_id
        or not chat_id
        or not user_id
        or not prompt
        or not query
        or not user_message
        or not tool_name
    ):
        logger.warning("Search requested payload missing required fields: %s", payload)
        return
    await Mediator.send_async(
        HandleSearchRequestCommand(
            search_session_id=str(search_session_id),
            source_request_id=str(source_request_id),
            chat_id=str(chat_id),
            user_id=str(user_id),
            chat_type=str(payload.get("chat_type")),
            prompt=str(prompt),
            query=str(query),
            tool_name=cast(ToolName, str(tool_name)),
            user_message=str(user_message),
            channel_id=str(payload.get("channel_id"))
            if payload.get("channel_id")
            else None,
            guild_id=str(payload.get("guild_id")) if payload.get("guild_id") else None,
            max_results=(
                int(payload["max_results"])
                if payload.get("max_results") is not None
                else None
            ),
        )
    )


@event_handler(CHAT_SEARCH_COMPLETED_TOPIC)
async def on_chat_search_completed(payload: dict[str, Any]) -> None:
    """Handle completed search and trigger re-generation."""
    search_session_id = payload.get("search_session_id")
    chat_id = payload.get("chat_id")
    prompt = payload.get("prompt")
    if not search_session_id or not chat_id:
        logger.warning("Search completed payload missing required fields: %s", payload)
        return
    if not prompt:
        prompt = ""
    chat_type_value = payload.get("chat_type")
    chat_type = ChatType.LINE
    if chat_type_value:
        chat_type_result = ChatType.from_primitive(str(chat_type_value))
        if is_err(chat_type_result):
            logger.warning("Invalid chat_type on search completed payload: %s", payload)
            return
        chat_type = chat_type_result.value
    await Mediator.send_async(
        GenerateContentWithRetrievedContextQuery(
            prompt=prompt,
            search_session_id=str(search_session_id),
            guild_id=str(payload.get("guild_id") or "LINE"),
            channel_id=str(payload.get("channel_id") or chat_id),
            user_id=str(payload.get("user_id") or chat_id),
            chat_type=chat_type,
        )
    )


@scheduled_task(interval_seconds=MEMORY_SLEEP_INTERVAL_SECONDS)
async def run_memory_sleep_scheduled_task() -> None:
    """Run the memory sleep job on a periodic schedule."""

    await Mediator.send_async(RunMemorySleepCommand())


cast(Any, run_memory_sleep_scheduled_task).schedule_run_time = MEMORY_SLEEP_RUN_TIME
