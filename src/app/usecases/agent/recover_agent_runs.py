"""Recover expired AgentRun and AgentToolCall leases."""

from dataclasses import dataclass
from datetime import UTC, datetime

from flow_med import Request, RequestHandler
from flow_res import Err, Ok, Result, is_err
from injector import inject

from app.contracts.messages.agent_run_events import (
    AGENT_RUN_WAKEUP_TOPIC,
    AGENT_TOOL_REQUESTED_TOPIC,
    build_agent_run_wakeup_payload,
    build_agent_tool_requested_payload,
    tool_request_event_id,
    wake_event_id,
)
from app.contracts.messages.use_case_error import ErrorType, UseCaseError
from app.contracts.ports.unit_of_work import IUnitOfWork


@dataclass
class RecoverAgentRunsCommand(Request[Result[int, UseCaseError]]):
    limit: int = 100


class RecoverAgentRunsHandler(
    RequestHandler[RecoverAgentRunsCommand, Result[int, UseCaseError]]
):
    @inject
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def handle(
        self, request: RecoverAgentRunsCommand
    ) -> Result[int, UseCaseError]:
        async with self._uow:
            recovered = await self._uow.GetAgentRunRepository().recover_due(
                now=datetime.now(UTC), limit=request.limit
            )
            if is_err(recovered):
                return Err(
                    UseCaseError(
                        type=ErrorType.UNEXPECTED, message=recovered.error.message
                    )
                )
            for run in recovered.value.runs:
                self._uow.enqueue_event(
                    AGENT_RUN_WAKEUP_TOPIC,
                    build_agent_run_wakeup_payload(
                        agent_run_id=run.id, wake_sequence=run.wake_sequence
                    ),
                    event_id=wake_event_id(run.id, run.wake_sequence),
                )
            for tool in recovered.value.tool_calls:
                self._uow.enqueue_event(
                    AGENT_TOOL_REQUESTED_TOPIC,
                    build_agent_tool_requested_payload(
                        agent_run_id=tool.agent_run_id,
                        tool_call_id=tool.id,
                        attempt_count=tool.attempt_count,
                    ),
                    event_id=tool_request_event_id(tool.id, tool.attempt_count),
                )
            committed = await self._uow.commit()
            if is_err(committed):
                return Err(
                    UseCaseError(
                        type=ErrorType.UNEXPECTED, message=committed.error.message
                    )
                )
        return Ok(len(recovered.value.runs) + len(recovered.value.tool_calls))
