"""Advance a durable agent run from a wakeup event."""

from dataclasses import dataclass

from flow_med import Request, RequestHandler
from flow_res import Err, Ok, Result, is_err
from injector import inject

from app.application.agent.run_coordinator import AgentRunCoordinator
from app.contracts.messages.use_case_error import ErrorType, UseCaseError


@dataclass
class AdvanceAgentRunCommand(Request[Result[bool, UseCaseError]]):
    agent_run_id: str
    wake_sequence: int


class AdvanceAgentRunHandler(
    RequestHandler[AdvanceAgentRunCommand, Result[bool, UseCaseError]]
):
    @inject
    def __init__(self, coordinator: AgentRunCoordinator) -> None:
        self._coordinator = coordinator

    async def handle(
        self, request: AdvanceAgentRunCommand
    ) -> Result[bool, UseCaseError]:
        result = await self._coordinator.advance(
            run_id=request.agent_run_id, wake_sequence=request.wake_sequence
        )
        if is_err(result):
            return Err(
                UseCaseError(type=ErrorType.UNEXPECTED, message=result.error.message)
            )
        return Ok(result.value)
