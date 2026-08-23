"""Tests for LINE entrypoint helpers."""

import json
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.usecases.conversation.accept_incoming_message import (
    AcceptIncomingMessageCommand,
)


def _load_line_main(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LINE_CHANNEL_SECRET", "secret")
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "token")
    module_name = "app.presentation.line.__main__"
    import sys

    sys.modules.pop(module_name, None)
    return import_module(module_name)


@pytest.mark.anyio
async def test_handle_callback_marks_message_as_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test LINE webhook handling on a successful read receipt."""
    line_main = _load_line_main(monkeypatch)

    monkeypatch.setattr(
        line_main.parser.signature_validator, "validate", Mock(return_value=True)
    )
    monkeypatch.setattr(
        line_main.Mediator, "send_async", AsyncMock(return_value=Mock())
    )
    monkeypatch.setattr(line_main, "is_err", Mock(return_value=False))

    line_bot_api = AsyncMock()
    line_bot_api.mark_messages_as_read_by_token = AsyncMock(return_value=None)
    request = SimpleNamespace(
        headers={"X-Line-Signature": "signature"},
        body=AsyncMock(
            return_value=json.dumps(
                {
                    "events": [
                        {
                            "type": "message",
                            "replyToken": "reply-token",
                            "source": {"type": "user", "userId": "u1"},
                            "message": {
                                "type": "text",
                                "text": "hello",
                                "markAsReadToken": "read-token",
                            },
                        }
                    ]
                }
            ).encode(),
        ),
        app=SimpleNamespace(state=SimpleNamespace(line_bot_api=line_bot_api)),
    )

    result = await line_main.handle_callback(request)

    assert result == "OK"
    line_bot_api.mark_messages_as_read_by_token.assert_awaited_once()
    request_model = line_bot_api.mark_messages_as_read_by_token.await_args.args[0]
    assert request_model.mark_as_read_token == "read-token"
    line_main.Mediator.send_async.assert_awaited_once()
    accept_command = line_main.Mediator.send_async.await_args.args[0]
    assert isinstance(accept_command, AcceptIncomingMessageCommand)
    assert accept_command.message.external_participant_id == "u1"
    assert accept_command.message.text == "hello"


@pytest.mark.anyio
async def test_handle_callback_saves_message_without_read_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing read token must not prevent durable message handling."""
    line_main = _load_line_main(monkeypatch)

    monkeypatch.setattr(
        line_main.parser.signature_validator, "validate", Mock(return_value=True)
    )
    monkeypatch.setattr(
        line_main.Mediator, "send_async", AsyncMock(return_value=Mock())
    )
    monkeypatch.setattr(line_main, "is_err", Mock(return_value=False))

    line_bot_api = AsyncMock()
    line_bot_api.mark_messages_as_read_by_token = AsyncMock(return_value=None)
    request = SimpleNamespace(
        headers={"X-Line-Signature": "signature"},
        body=AsyncMock(
            return_value=json.dumps(
                {
                    "events": [
                        {
                            "type": "message",
                            "replyToken": "reply-token",
                            "source": {"type": "user", "userId": "u1"},
                            "message": {"type": "text", "text": "hello"},
                        }
                    ]
                }
            ).encode(),
        ),
        app=SimpleNamespace(state=SimpleNamespace(line_bot_api=line_bot_api)),
    )

    result = await line_main.handle_callback(request)

    assert result == "OK"
    line_bot_api.mark_messages_as_read_by_token.assert_not_awaited()
    line_main.Mediator.send_async.assert_awaited_once()
    accept_command = line_main.Mediator.send_async.await_args.args[0]
    assert isinstance(accept_command, AcceptIncomingMessageCommand)
    assert accept_command.message.external_participant_id == "u1"
    assert accept_command.message.text == "hello"
