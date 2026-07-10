"""Accept a saved chat into its durable conversation mailbox."""

from __future__ import annotations

from dataclasses import dataclass

from flow_med import Request, RequestHandler
from flow_res import Err, Ok, Result, is_err
from injector import inject

from app.contracts.messages.agent_run_events import (
    AGENT_RUN_WAKEUP_TOPIC,
    build_agent_run_wakeup_payload,
    wake_event_id,
)
from app.contracts.messages.chat_type import ChatType
from app.contracts.messages.use_case_error import ErrorType, UseCaseError
from app.contracts.ports.unit_of_work import IUnitOfWork


@dataclass
class StartAgentRunCommand(Request[Result[str, UseCaseError]]):
    """Accept one source chat message idempotently."""

    chat_id: str
    user_id: str
    chat_type: ChatType
    guild_id: str
    channel_id: str
    character_id: str


class StartAgentRunHandler(
    RequestHandler[StartAgentRunCommand, Result[str, UseCaseError]]
):
    """Persist a run and wake it only when its conversation mailbox is free."""

    @inject
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def handle(self, request: StartAgentRunCommand) -> Result[str, UseCaseError]:
        conversation_id = (
            request.user_id
            if request.chat_type is ChatType.LINE
            else f"{request.guild_id}:{request.channel_id}"
        )
        conversation_key = (
            f"{request.character_id}:{request.chat_type.value}:{conversation_id}"
        )
        async with self._uow:
            started = await self._uow.GetAgentRunRepository().start(
                conversation_key=conversation_key,
                source_chat_id=request.chat_id,
                character_id=request.character_id,
                user_id=request.user_id,
                chat_type=request.chat_type,
                guild_id=request.guild_id,
                channel_id=request.channel_id,
                max_turns=8,
            )
            if is_err(started):
                return Err(
                    UseCaseError(
                        type=ErrorType.UNEXPECTED, message=started.error.message
                    )
                )
            if started.value.should_wake:
                run = started.value.run
                self._uow.enqueue_event(
                    AGENT_RUN_WAKEUP_TOPIC,
                    build_agent_run_wakeup_payload(
                        agent_run_id=run.id, wake_sequence=run.wake_sequence
                    ),
                    event_id=wake_event_id(run.id, run.wake_sequence),
                )
            committed = await self._uow.commit()
            if is_err(committed):
                return Err(
                    UseCaseError(
                        type=ErrorType.UNEXPECTED, message=committed.error.message
                    )
                )
        return Ok(started.value.run.id)
