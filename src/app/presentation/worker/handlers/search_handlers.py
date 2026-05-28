"""Worker handlers for search events."""

import logging
from collections.abc import Mapping
from typing import cast

from flow_med import Mediator
from flow_res import is_err

from app.contracts.messages.chat_events import (
    CHAT_SEARCH_COMPLETED_TOPIC,
    CHAT_SEARCH_REQUESTED_TOPIC,
)
from app.contracts.messages.tool_use import ToolName
from app.domain.value_objects.chat_type import ChatType
from app.presentation.worker.registry import event_handler
from app.usecases.chat.generate_content_with_retrieved_context import (
    GenerateContentWithRetrievedContextQuery,
)
from app.usecases.search.handle_search_request import HandleSearchRequestCommand

logger = logging.getLogger(__name__)


def _require_str(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str) and value:
        return value
    return None


def _require_int(payload: Mapping[str, object], key: str) -> int | None:
    value = payload.get(key)
    if isinstance(value, int):
        return value
    return None


@event_handler(CHAT_SEARCH_REQUESTED_TOPIC)
async def on_chat_search_requested(payload: Mapping[str, object]) -> None:
    """Handle a requested search."""

    search_session_id = _require_str(payload, "search_session_id")
    source_request_id = _require_str(payload, "source_request_id")
    chat_id = _require_str(payload, "chat_id")
    user_id = _require_str(payload, "user_id")
    prompt = _require_str(payload, "prompt")
    query = _require_str(payload, "query")
    user_message = _require_str(payload, "user_message")
    tool_name = _require_str(payload, "tool_name")
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
            chat_type=_require_str(payload, "chat_type") or "",
            prompt=str(prompt),
            query=str(query),
            tool_name=cast(ToolName, str(tool_name)),
            user_message=str(user_message),
            channel_id=_require_str(payload, "channel_id"),
            guild_id=_require_str(payload, "guild_id"),
            max_results=_require_int(payload, "max_results"),
        )
    )


@event_handler(CHAT_SEARCH_COMPLETED_TOPIC)
async def on_chat_search_completed(payload: Mapping[str, object]) -> None:
    """Handle completed search and trigger re-generation."""

    search_session_id = _require_str(payload, "search_session_id")
    chat_id = _require_str(payload, "chat_id")
    prompt = _require_str(payload, "prompt")
    if not search_session_id or not chat_id:
        logger.warning("Search completed payload missing required fields: %s", payload)
        return
    if not prompt:
        prompt = ""
    chat_type_value = _require_str(payload, "chat_type")
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
            guild_id=_require_str(payload, "guild_id") or "LINE",
            channel_id=_require_str(payload, "channel_id") or chat_id,
            user_id=_require_str(payload, "user_id") or chat_id,
            chat_type=chat_type,
        )
    )
