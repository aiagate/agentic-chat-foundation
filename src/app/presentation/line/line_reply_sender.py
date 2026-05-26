"""LINE reply sender helpers."""

from __future__ import annotations

import logging
from typing import Any

from linebot.v3.messaging import AsyncMessagingApi, PushMessageRequest, TextMessage

logger = logging.getLogger(__name__)


async def send_line_reply(
    line_bot_api: AsyncMessagingApi,
    payload: dict[str, Any],
) -> None:
    """Send generated replies to a LINE destination."""
    contents = _normalize_contents(payload)
    target_user_id = (
        payload.get("user_id") or payload.get("group_id") or payload.get("room_id")
    )
    if not contents or not target_user_id:
        logger.warning("LINE reply payload missing required fields: %s", payload)
        return

    for content in contents:
        await line_bot_api.push_message(
            PushMessageRequest(
                to=str(target_user_id),
                messages=[
                    TextMessage(
                        text=content,
                        quickReply=None,
                        quoteToken=None,
                    )
                ],
                notificationDisabled=False,
                customAggregationUnits=None,
            )
        )


def _normalize_contents(payload: dict[str, Any]) -> list[str]:
    contents = payload.get("contents")
    if isinstance(contents, list):
        return [str(content) for content in contents if content]

    content = payload.get("content")
    if content:
        return [str(content)]
    return []
