"""Presentation-facing serial conversation flow adapter."""

from __future__ import annotations

from flow_res import Err, Ok, Result, is_err

from app.contracts.messages.conversation import DeliveryResult, IncomingMessage
from app.contracts.messages.use_case_error import UseCaseError
from app.contracts.ports.conversation import (
    ConversationContext,
    ConversationHistory,
    ConversationResultSender,
    ResponseGenerator,
)
from app.contracts.ports.relationship import IRelationshipInteractionProcessor
from app.contracts.ports.user_identity_query import IUserIdentityQuery
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


class ConversationFlow:
    """Run the three conversation UCs serially in the request process."""

    def __init__(
        self,
        history: ConversationHistory,
        context: ConversationContext,
        generator: ResponseGenerator,
        user_identity_query: IUserIdentityQuery,
        relationship_processor: IRelationshipInteractionProcessor,
    ) -> None:
        self._history = history
        self._context = context
        self._generator = generator
        self._user_identity_query = user_identity_query
        self._relationship_processor = relationship_processor

    async def process(
        self,
        message: IncomingMessage,
        sender: ConversationResultSender,
    ) -> Result[DeliveryResult, UseCaseError]:
        accepted = await AcceptIncomingMessageHandler(
            self._history, self._user_identity_query
        ).handle(AcceptIncomingMessageCommand(message))
        if is_err(accepted):
            return Err(accepted.error)
        if not accepted.value.is_new:
            return Ok(
                DeliveryResult(message_id=accepted.value.message_id, delivered=True)
            )

        created = await CreateConversationResponseHandler(
            self._context, self._generator, self._relationship_processor
        ).handle(CreateConversationResponseCommand(accepted.value))
        if is_err(created):
            return Err(created.error)
        return await DeliverConversationResultHandler(sender, self._history).handle(
            DeliverConversationResultCommand(created.value, accepted.value)
        )
