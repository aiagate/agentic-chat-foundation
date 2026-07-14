"""UC-02: create one response for an accepted message."""

from dataclasses import dataclass

from flow_med import Request, RequestHandler
from flow_res import Err, Ok, Result

from app.contracts.messages.conversation import AcceptedMessage, ConversationResult
from app.contracts.messages.use_case_error import ErrorType, UseCaseError
from app.contracts.ports.conversation import ConversationContext, ResponseGenerator


@dataclass(frozen=True, slots=True)
class CreateConversationResponseCommand(
    Request[Result[ConversationResult, UseCaseError]]
):
    message: AcceptedMessage


class CreateConversationResponseHandler(
    RequestHandler[
        CreateConversationResponseCommand,
        Result[ConversationResult, UseCaseError],
    ]
):
    def __init__(
        self,
        context: ConversationContext,
        generator: ResponseGenerator,
    ) -> None:
        self._context = context
        self._generator = generator

    async def handle(
        self, request: CreateConversationResponseCommand
    ) -> Result[ConversationResult, UseCaseError]:
        try:
            context = await self._context.load(request.message)
            result = await self._generator.generate(request.message, context)
            return Ok(result)
        except Exception as exc:
            return Err(UseCaseError(ErrorType.UNEXPECTED, f"Response unavailable: {exc}"))
