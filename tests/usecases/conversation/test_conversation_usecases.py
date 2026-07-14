from dataclasses import dataclass

import pytest
from flow_res import is_err

from app.contracts.messages.conversation import (
    AcceptedMessage,
    ConversationResult,
    DeliveryResult,
    IncomingMessage,
)
from app.usecases.conversation.accept_incoming_message import (
    AcceptIncomingMessageCommand,
    AcceptIncomingMessageHandler,
)
from app.usecases.conversation.create_conversation_response import (
    CreateConversationResponseCommand,
    CreateConversationResponseHandler,
)
from app.usecases.conversation.deliver_conversation_result import (
    DeliverConversationResultCommand,
    DeliverConversationResultHandler,
)


@dataclass
class FakeHistory:
    accepted: AcceptedMessage
    assistant_messages: list[ConversationResult] | None = None

    async def append(self, message: IncomingMessage) -> AcceptedMessage:
        return self.accepted

    async def append_assistant(
        self,
        message: AcceptedMessage,
        result: ConversationResult,
    ) -> None:
        if self.assistant_messages is not None:
            self.assistant_messages.append(result)


class FakeContext:
    async def load(self, message: AcceptedMessage) -> object:
        return {"message_id": message.message_id}


class FakeGenerator:
    async def generate(
        self, message: AcceptedMessage, context: object
    ) -> ConversationResult:
        return ConversationResult(
            message_id=message.message_id,
            conversation_id=message.conversation_id,
            channel=message.channel,
            contents=("ok",),
        )


class FakeSender:
    async def send(self, result: ConversationResult) -> DeliveryResult:
        return DeliveryResult(message_id=result.message_id, delivered=True)


def incoming() -> IncomingMessage:
    return IncomingMessage(
        channel="test",
        external_conversation_id="conversation",
        external_participant_id="participant",
        text="hello",
        external_message_id="external-message",
    )


def accepted() -> AcceptedMessage:
    return AcceptedMessage(
        message_id="message",
        conversation_id="conversation",
        participant_id="participant",
        text="hello",
        channel="test",
        occurred_at=incoming().occurred_at,
    )


@pytest.mark.asyncio
async def test_accept_rejects_blank_text() -> None:
    result = await AcceptIncomingMessageHandler(FakeHistory(accepted())).handle(
        AcceptIncomingMessageCommand(IncomingMessage(
            channel="test",
            external_conversation_id="conversation",
            external_participant_id="participant",
            text=" ",
            external_message_id="external-message",
        ))
    )

    assert is_err(result)


@pytest.mark.asyncio
async def test_conversation_flow_returns_delivery_result() -> None:
    history = FakeHistory(accepted(), assistant_messages=[])
    accepted_result = await AcceptIncomingMessageHandler(history).handle(
        AcceptIncomingMessageCommand(incoming())
    )
    assert not is_err(accepted_result)

    response_result = await CreateConversationResponseHandler(
        FakeContext(), FakeGenerator()
    ).handle(CreateConversationResponseCommand(accepted_result.value))
    assert not is_err(response_result)

    delivery_result = await DeliverConversationResultHandler(
        FakeSender(), history
    ).handle(
        DeliverConversationResultCommand(
            result=response_result.value,
            message=accepted_result.value,
        )
    )
    assert not is_err(delivery_result)
    assert delivery_result.value.delivered is True
    assert history.assistant_messages == [response_result.value]


@pytest.mark.asyncio
async def test_assistant_history_is_not_saved_when_delivery_fails() -> None:
    class FailingSender:
        async def send(self, result: ConversationResult) -> DeliveryResult:
            return DeliveryResult(
                message_id=result.message_id,
                delivered=False,
                failure_reason="channel unavailable",
            )

    history = FakeHistory(accepted(), assistant_messages=[])
    result = ConversationResult(
        message_id="message",
        conversation_id="conversation",
        channel="test",
        contents=("ok",),
    )
    delivery = await DeliverConversationResultHandler(
        FailingSender(), history
    ).handle(
        DeliverConversationResultCommand(result=result, message=accepted())
    )

    assert is_err(delivery)
    assert history.assistant_messages == []
