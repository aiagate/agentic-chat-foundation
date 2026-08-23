"""Create one response for an accepted message."""

import asyncio
import logging
from dataclasses import dataclass

from flow_med import Request, RequestHandler
from flow_res import Err, Ok, Result

from app.contracts.messages.conversation import AcceptedMessage, ConversationResult
from app.contracts.messages.use_case_error import ErrorType, UseCaseError
from app.contracts.ports.conversation import ConversationContext, ResponseGenerator
from app.contracts.ports.relationship import IRelationshipInteractionProcessor

logger = logging.getLogger(__name__)


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
        relationship_processor: IRelationshipInteractionProcessor,
    ) -> None:
        self._context = context
        self._generator = generator
        self._relationship_processor = relationship_processor

    async def handle(
        self, request: CreateConversationResponseCommand
    ) -> Result[ConversationResult, UseCaseError]:
        try:
            context = await self._context.load(request.message)
            generated, relationship_result = await asyncio.gather(
                self._generator.generate(request.message, context),
                self._relationship_processor.process(request.message),
                return_exceptions=True,
            )
            if isinstance(relationship_result, Exception):
                logger.warning(
                    "Immediate relationship evaluation failed",
                    exc_info=relationship_result,
                    extra={
                        "message_id": request.message.message_id,
                        "character_id": request.message.character_id,
                        "user_id": request.message.user_id,
                    },
                )
            if isinstance(generated, BaseException):
                raise generated
            return Ok(generated)
        except Exception as exc:
            return Err(
                UseCaseError(ErrorType.UNEXPECTED, f"Response unavailable: {exc}")
            )
