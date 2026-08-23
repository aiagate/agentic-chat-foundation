"""Accept an incoming text message."""

from dataclasses import dataclass

from flow_med import Request, RequestHandler
from flow_res import Err, Ok, Result, is_err

from app.contracts.messages.conversation import AcceptedMessage, IncomingMessage
from app.contracts.messages.use_case_error import ErrorType, UseCaseError
from app.contracts.ports.conversation import ConversationHistory
from app.contracts.ports.user_identity_query import IUserIdentityQuery
from app.domain.aggregates.user import UserChannelIdentity


@dataclass(frozen=True, slots=True)
class AcceptIncomingMessageCommand(Request[Result[AcceptedMessage, UseCaseError]]):
    message: IncomingMessage


class AcceptIncomingMessageHandler(
    RequestHandler[
        AcceptIncomingMessageCommand,
        Result[AcceptedMessage, UseCaseError],
    ]
):
    def __init__(
        self,
        history: ConversationHistory,
        user_identity_query: IUserIdentityQuery,
    ) -> None:
        self._history = history
        self._user_identity_query = user_identity_query

    async def handle(
        self, request: AcceptIncomingMessageCommand
    ) -> Result[AcceptedMessage, UseCaseError]:
        if not request.message.text.strip():
            return Err(
                UseCaseError(ErrorType.VALIDATION_ERROR, "Message text is empty")
            )
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
            identity = UserChannelIdentity(
                channel=request.message.channel,
                external_participant_id=request.message.external_participant_id,
            )
        except ValueError as exc:
            return Err(UseCaseError(ErrorType.VALIDATION_ERROR, str(exc)))
        resolved = await self._user_identity_query.find_user(identity)
        if is_err(resolved):
            return Err(UseCaseError(ErrorType.UNEXPECTED, resolved.error.message))
        if resolved.value is None:
            return Err(
                UseCaseError(
                    ErrorType.NOT_FOUND,
                    "External participant is not registered",
                )
            )
        try:
            return Ok(
                await self._history.append(request.message, user_id=resolved.value.id)
            )
        except Exception as exc:
            return Err(UseCaseError(ErrorType.UNEXPECTED, str(exc)))
