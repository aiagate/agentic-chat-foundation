"""Tests for LINE reply sender helpers."""

from unittest.mock import AsyncMock

import pytest
from linebot.v3.messaging import AsyncMessagingApi, PushMessageRequest, TextMessage

from app.presentation.line.line_reply_sender import send_line_reply


@pytest.mark.anyio
async def test_send_line_reply_pushes_message() -> None:
    """Test LINE reply dispatch to a push message."""
    line_bot_api = AsyncMock(spec=AsyncMessagingApi)
    line_bot_api.push_message = AsyncMock(return_value=None)

    await send_line_reply(
        line_bot_api,
        {
            "user_id": "U123",
            "contents": ["hello", "world"],
        },
    )

    assert line_bot_api.push_message.await_count == 2
    first_request = line_bot_api.push_message.await_args_list[0].args[0]
    second_request = line_bot_api.push_message.await_args_list[1].args[0]
    assert isinstance(first_request, PushMessageRequest)
    assert isinstance(second_request, PushMessageRequest)
    assert first_request.to == "U123"
    assert second_request.to == "U123"
    assert isinstance(first_request.messages[0], TextMessage)
    assert isinstance(second_request.messages[0], TextMessage)
    assert first_request.messages[0].text == "hello"
    assert second_request.messages[0].text == "world"
