"""Handle a requested search workflow."""

from __future__ import annotations

from dataclasses import dataclass

from flow_med import Mediator, Request, RequestHandler
from flow_res import Err, Ok, Result, is_err
from injector import inject

from app.contracts.messages.chat_events import (
    CHAT_SEARCH_COMPLETED_TOPIC,
    build_chat_search_completed_payload,
)
from app.contracts.messages.tool_use import ToolName
from app.contracts.ports.event_bus import IEventBus
from app.usecases.result import ErrorType, UseCaseError
from app.usecases.search.run_web_search import RunWebSearchCommand


@dataclass(frozen=True)
class HandleSearchRequestResult:
    """Result metadata for a handled search request."""

    result_count: int


@dataclass
class HandleSearchRequestCommand(
    Request[Result[HandleSearchRequestResult, UseCaseError]]
):
    """Handle the search request emitted by chat generation."""

    search_session_id: str
    source_request_id: str
    chat_id: str
    user_id: str
    chat_type: str
    prompt: str
    query: str
    tool_name: ToolName
    user_message: str
    channel_id: str | None = None
    guild_id: str | None = None
    max_results: int | None = None


class HandleSearchRequestHandler(
    RequestHandler[
        HandleSearchRequestCommand,
        Result[HandleSearchRequestResult, UseCaseError],
    ]
):
    """Bridge from search request event to the search execution usecase."""

    @inject
    def __init__(self, event_bus: IEventBus) -> None:
        self._event_bus = event_bus

    async def handle(
        self, request: HandleSearchRequestCommand
    ) -> Result[HandleSearchRequestResult, UseCaseError]:
        """Execute search and emit completion."""
        run_result = await Mediator.send_async(
            RunWebSearchCommand(
                search_session_id=request.search_session_id,
                query=request.query,
                user_message=request.user_message,
                source_request_id=request.source_request_id,
                max_results=request.max_results,
                tool_name=request.tool_name,
            )
        )
        if is_err(run_result):
            await self._event_bus.publish(
                CHAT_SEARCH_COMPLETED_TOPIC,
                build_chat_search_completed_payload(
                    search_session_id=request.search_session_id,
                    source_request_id=request.source_request_id,
                    chat_id=request.chat_id,
                    chat_type=request.chat_type,
                    user_id=request.user_id,
                    prompt=request.prompt,
                    status="error",
                    result_count=0,
                    tool_name=request.tool_name,
                    error=str(run_result.error),
                    guild_id=request.guild_id,
                    channel_id=request.channel_id,
                ),
            )
            return Err(
                UseCaseError(
                    type=ErrorType.UNEXPECTED,
                    message="Failed to run search request",
                )
            )

        await self._event_bus.publish(
            CHAT_SEARCH_COMPLETED_TOPIC,
            build_chat_search_completed_payload(
                search_session_id=request.search_session_id,
                source_request_id=request.source_request_id,
                chat_id=request.chat_id,
                chat_type=request.chat_type,
                user_id=request.user_id,
                prompt=request.prompt,
                status="ok",
                result_count=run_result.value.result_count,
                tool_name=request.tool_name,
                guild_id=request.guild_id,
                channel_id=request.channel_id,
            ),
        )
        return Ok(HandleSearchRequestResult(result_count=run_result.value.result_count))
