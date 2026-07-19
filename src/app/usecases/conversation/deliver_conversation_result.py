"""Deliver a logical conversation result."""

from dataclasses import dataclass

from flow_med import Request, RequestHandler
from flow_res import Err, Ok, Result

from app.contracts.messages.conversation import (
    AcceptedMessage,
    ConversationResult,
    DeliveryResult,
)
from app.contracts.messages.use_case_error import ErrorType, UseCaseError
from app.contracts.ports.conversation import (
    ConversationHistory,
    ConversationResultSender,
)


@dataclass(frozen=True, slots=True)
class DeliverConversationResultCommand(Request[Result[DeliveryResult, UseCaseError]]):
    result: ConversationResult
    message: AcceptedMessage


class DeliverConversationResultHandler(
    RequestHandler[
        DeliverConversationResultCommand,
        Result[DeliveryResult, UseCaseError],
    ]
):
    def __init__(
        self,
        sender: ConversationResultSender,
        history: ConversationHistory,
    ) -> None:
        self._sender = sender
        self._history = history

    async def handle(
        self, request: DeliverConversationResultCommand
    ) -> Result[DeliveryResult, UseCaseError]:
        try:
            delivery = await self._sender.send(request.result)
        except Exception as exc:
            return Err(UseCaseError(ErrorType.UNEXPECTED, str(exc)))
        if not delivery.delivered:
            return Err(
                UseCaseError(
                    ErrorType.UNEXPECTED,
                    delivery.failure_reason or "Failed to deliver conversation result",
                )
            )
        try:
            await self._history.append_assistant(request.message, request.result)
        except Exception as exc:
            return Err(
                UseCaseError(
                    ErrorType.UNEXPECTED,
                    f"Assistant history could not be saved: {exc}",
                )
            )
        return Ok(delivery)
