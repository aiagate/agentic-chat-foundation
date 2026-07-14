"""Tests for the request-local UC-01 to UC-03 orchestration."""

from datetime import UTC, datetime

import pytest
from flow_res import is_err

from app.contracts.messages.conversation import (
    AcceptedMessage,
    ConversationResult,
    DeliveryResult,
    IncomingMessage,
)
from app.presentation.conversation_flow import ConversationFlow


class _History:
    def __init__(self) -> None:
        self.assistant: list[ConversationResult] = []

    async def append(self, message: IncomingMessage) -> AcceptedMessage:
        return AcceptedMessage(
            message_id="chat-1",
            conversation_id=message.external_conversation_id,
            participant_id=message.external_participant_id,
            text=message.text,
            channel=message.channel,
            occurred_at=message.occurred_at,
            metadata=message.metadata,
        )

    async def append_assistant(
        self, message: AcceptedMessage, result: ConversationResult
    ) -> None:
        self.assistant.append(result)


class _Context:
    async def load(self, message: AcceptedMessage) -> object:
        return {"message_id": message.message_id}


class _Generator:
    async def generate(
        self, message: AcceptedMessage, context: object
    ) -> ConversationResult:
        return ConversationResult(
            message_id=message.message_id,
            conversation_id=message.conversation_id,
            channel=message.channel,
            contents=("hello",),
        )


class _Sender:
    async def send(self, result: ConversationResult) -> DeliveryResult:
        return DeliveryResult(message_id=result.message_id, delivered=True)


@pytest.mark.anyio
async def test_flow_delivers_then_persists_assistant() -> None:
    history = _History()
    result = await ConversationFlow(history, _Context(), _Generator()).process(
        IncomingMessage(
            channel="discord",
            external_conversation_id="channel-1",
            external_participant_id="user-1",
            text="hello",
            external_message_id="message-1",
            occurred_at=datetime.now(UTC),
        ),
        _Sender(),
    )

    assert not is_err(result)
    assert result.value.delivered is True
    assert [item.contents for item in history.assistant] == [("hello",)]
