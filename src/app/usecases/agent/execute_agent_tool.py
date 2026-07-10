"""Execute a durable AgentToolCall from its transport event."""

from dataclasses import dataclass

from flow_med import Request, RequestHandler
from flow_res import Err, Ok, Result, is_err
from injector import inject

from app.application.agent.tool_coordinator import AgentToolCoordinator
from app.contracts.messages.use_case_error import ErrorType, UseCaseError


@dataclass
class ExecuteAgentToolCommand(Request[Result[bool, UseCaseError]]):
    agent_run_id: str
    tool_call_id: str
    attempt_count: int


class ExecuteAgentToolHandler(
    RequestHandler[ExecuteAgentToolCommand, Result[bool, UseCaseError]]
):
    @inject
    def __init__(self, coordinator: AgentToolCoordinator) -> None:
        self._coordinator = coordinator

    async def handle(
        self, request: ExecuteAgentToolCommand
    ) -> Result[bool, UseCaseError]:
        result = await self._coordinator.execute(
            run_id=request.agent_run_id,
            tool_call_id=request.tool_call_id,
            attempt_count=request.attempt_count,
        )
        if is_err(result):
            return Err(
                UseCaseError(type=ErrorType.UNEXPECTED, message=result.error.message)
            )
        return Ok(result.value)
