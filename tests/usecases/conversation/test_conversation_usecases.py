from dataclasses import dataclass

import pytest
from flow_res import Ok, Result, is_err

from app.contracts.messages.conversation import (
    AcceptedMessage,
    ConversationResult,
    DeliveryResult,
    IncomingMessage,
)
from app.contracts.ports.relationship import IRelationshipInteractionProcessor
from app.contracts.ports.user_identity_query import IUserIdentityQuery
from app.domain.aggregates.user import User, UserChannelIdentity
from app.domain.repositories.interfaces import RepositoryError
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

    async def append(
        self, message: IncomingMessage, *, user_id: str
    ) -> AcceptedMessage:
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
            external_conversation_id=message.external_conversation_id,
            channel=message.channel,
            contents=("ok",),
        )


class FakeSender:
    async def send(self, result: ConversationResult) -> DeliveryResult:
        return DeliveryResult(message_id=result.message_id, delivered=True)


class FakeRelationshipProcessor(IRelationshipInteractionProcessor):
    async def process(self, message: AcceptedMessage) -> None:
        del message


class FailingRelationshipProcessor(IRelationshipInteractionProcessor):
    async def process(self, message: AcceptedMessage) -> None:
        del message
        raise RuntimeError("relationship evaluator unavailable")


def incoming() -> IncomingMessage:
    return IncomingMessage(
        channel="discord",
        external_conversation_id="conversation",
        external_participant_id="participant",
        text="hello",
        external_message_id="external-message",
    )


def accepted() -> AcceptedMessage:
    return AcceptedMessage(
        message_id="message",
        character_id="shirasagi-reina",
        user_id="01J00000000000000000000000",
        external_conversation_id="conversation",
        external_participant_id="participant",
        text="hello",
        channel="discord",
        occurred_at=incoming().occurred_at,
    )


class FakeIdentityQuery(IUserIdentityQuery):
    async def find_user(
        self, identity: UserChannelIdentity
    ) -> Result[User | None, RepositoryError]:
        return Ok(User(id="01J00000000000000000000000", identities=(identity,)))


class MissingIdentityQuery(IUserIdentityQuery):
    async def find_user(
        self, identity: UserChannelIdentity
    ) -> Result[User | None, RepositoryError]:
        del identity
        return Ok(None)


class HistoryMustNotAppend(FakeHistory):
    async def append(
        self, message: IncomingMessage, *, user_id: str
    ) -> AcceptedMessage:
        del message, user_id
        raise AssertionError("Unregistered input must fail before raw persistence")


@pytest.mark.asyncio
async def test_accept_rejects_blank_text() -> None:
    result = await AcceptIncomingMessageHandler(
        FakeHistory(accepted()), FakeIdentityQuery()
    ).handle(
        AcceptIncomingMessageCommand(
            IncomingMessage(
                channel="discord",
                external_conversation_id="conversation",
                external_participant_id="participant",
                text=" ",
                external_message_id="external-message",
            )
        )
    )

    assert is_err(result)


@pytest.mark.asyncio
async def test_accept_rejects_unregistered_user_before_persistence() -> None:
    result = await AcceptIncomingMessageHandler(
        HistoryMustNotAppend(accepted()), MissingIdentityQuery()
    ).handle(AcceptIncomingMessageCommand(incoming()))

    assert is_err(result)
    assert result.error.type.name == "NOT_FOUND"


@pytest.mark.asyncio
async def test_conversation_flow_returns_delivery_result() -> None:
    history = FakeHistory(accepted(), assistant_messages=[])
    accepted_result = await AcceptIncomingMessageHandler(
        history, FakeIdentityQuery()
    ).handle(AcceptIncomingMessageCommand(incoming()))
    assert not is_err(accepted_result)

    response_result = await CreateConversationResponseHandler(
        FakeContext(), FakeGenerator(), FakeRelationshipProcessor()
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
async def test_relationship_evaluation_failure_does_not_fail_response() -> None:
    result = await CreateConversationResponseHandler(
        FakeContext(), FakeGenerator(), FailingRelationshipProcessor()
    ).handle(CreateConversationResponseCommand(accepted()))

    assert not is_err(result)
    assert result.value.contents == ("ok",)


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
        external_conversation_id="conversation",
        channel="test",
        contents=("ok",),
    )
    delivery = await DeliverConversationResultHandler(FailingSender(), history).handle(
        DeliverConversationResultCommand(result=result, message=accepted())
    )

    assert is_err(delivery)
    assert history.assistant_messages == []
