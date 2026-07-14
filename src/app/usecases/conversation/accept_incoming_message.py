"""UC-01: accept an incoming text message."""

from dataclasses import dataclass

from flow_med import Request, RequestHandler
from flow_res import Err, Ok, Result

from app.contracts.messages.conversation import AcceptedMessage, IncomingMessage
from app.contracts.messages.use_case_error import ErrorType, UseCaseError
from app.contracts.ports.conversation import ConversationHistory


@dataclass(frozen=True, slots=True)
class AcceptIncomingMessageCommand(
    Request[Result[AcceptedMessage, UseCaseError]]
):
    message: IncomingMessage


class AcceptIncomingMessageHandler(
    RequestHandler[
        AcceptIncomingMessageCommand,
        Result[AcceptedMessage, UseCaseError],
    ]
):
    def __init__(self, history: ConversationHistory) -> None:
        self._history = history

    async def handle(
        self, request: AcceptIncomingMessageCommand
    ) -> Result[AcceptedMessage, UseCaseError]:
        if not request.message.text.strip():
            return Err(UseCaseError(ErrorType.VALIDATION_ERROR, "Message text is empty"))
        if request.message.channel.strip().lower() in {"discord", "line"} and not (
            request.message.external_message_id
            and request.message.external_message_id.strip()
        ):
            return Err(
                UseCaseError(
                    ErrorType.VALIDATION_ERROR,
                    "External message id is required",
                )
            )
        try:
            return Ok(await self._history.append(request.message))
        except Exception as exc:
            return Err(UseCaseError(ErrorType.UNEXPECTED, str(exc)))
