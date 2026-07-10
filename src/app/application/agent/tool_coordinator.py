"""Durable claim/execute/apply coordination for agent tools."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from flow_res import Err, Ok, Result, is_err

from app.application.agent.reply_persistence import AgentReplyPersistence
from app.contracts.messages.agent_run import AgentRunSnapshot
from app.contracts.messages.agent_run_events import (
    AGENT_RUN_WAKEUP_TOPIC,
    build_agent_run_wakeup_payload,
    wake_event_id,
)
from app.contracts.messages.tool_contracts import normalize_reply_contents
from app.contracts.ports.tool_executor import IToolExecutor, ToolExecutionContext
from app.contracts.ports.unit_of_work import IUnitOfWork


@dataclass(frozen=True, slots=True)
class AgentToolWorkflowError(Exception):
    """Failure to execute or apply one durable tool call."""

    message: str


class AgentToolCoordinator:
    """Execute a persisted tool call without using Redis as workflow state."""

    def __init__(
        self,
        uow: IUnitOfWork,
        tool_executor: IToolExecutor,
        reply_persistence: AgentReplyPersistence,
    ) -> None:
        self._uow = uow
        self._tool_executor = tool_executor
        self._reply_persistence = reply_persistence

    async def execute(
        self, *, run_id: str, tool_call_id: str, attempt_count: int
    ) -> Result[bool, AgentToolWorkflowError]:
        now = datetime.now(UTC)
        async with self._uow:
            claimed = await self._uow.GetAgentRunRepository().claim_tool_call(
                run_id=run_id,
                tool_call_id=tool_call_id,
                attempt_count=attempt_count,
                now=now,
                lease_expires_at=now + timedelta(minutes=5),
            )
            if is_err(claimed):
                return Err(AgentToolWorkflowError(claimed.error.message))
            if claimed.value is None:
                return Ok(False)
            commit = await self._uow.commit()
            if is_err(commit):
                return Err(AgentToolWorkflowError(commit.error.message))
            run, tool = claimed.value

        terminal_contents = (
            normalize_reply_contents(tool.tool_call.arguments)
            if tool.continuation == "terminal"
            else None
        )
        if tool.continuation == "terminal":
            succeeded = terminal_contents is not None
            result: dict[str, object] = {"content_count": len(terminal_contents or [])}
            error_message = None if succeeded else "Tool call content must not be empty"
            rendered = str(result) if succeeded else error_message
        else:
            execution = await self._tool_executor.execute(
                ToolExecutionContext(
                    chat_id=run.source_chat_id,
                    user_id=run.user_id,
                    chat_type=run.chat_type,
                    tool_call=tool.tool_call,
                    character_id=run.character_id,
                    guild_id=run.guild_id,
                    channel_id=run.channel_id,
                    agent_context=tool.tool_call,
                )
            )
            if is_err(execution):
                succeeded = False
                result = {}
                error_message = execution.error.message
                rendered = f"{tool.tool_call.tool_name} failed: {error_message}"
            else:
                succeeded = True
                result = dict(execution.value.result)
                error_message = None
                rendered = execution.value.rendered_text or str(result)

        now = datetime.now(UTC)
        async with self._uow:
            if succeeded and terminal_contents is not None:
                reply = await self._reply_persistence.write(
                    run=run,
                    contents=terminal_contents,
                    tool_call_id=tool.id,
                )
                if is_err(reply):
                    return Err(AgentToolWorkflowError(reply.error.message))
            applied = await self._uow.GetAgentRunRepository().complete_tool_call(
                run_id=run_id,
                tool_call_id=tool_call_id,
                lease_token=tool.lease_token or "",
                succeeded=succeeded,
                result=result,
                rendered_result=rendered or "Tool execution produced no result",
                error_code=None if succeeded else "tool_execution_failed",
                error_message=error_message,
                now=now,
            )
            if is_err(applied):
                return Err(AgentToolWorkflowError(applied.error.message))
            if applied.value is not None:
                self._enqueue_wakeup(applied.value)
            commit = await self._uow.commit()
            if is_err(commit):
                return Err(AgentToolWorkflowError(commit.error.message))
        return Ok(True)

    def _enqueue_wakeup(self, run: AgentRunSnapshot) -> None:
        self._uow.enqueue_event(
            AGENT_RUN_WAKEUP_TOPIC,
            build_agent_run_wakeup_payload(
                agent_run_id=run.id, wake_sequence=run.wake_sequence
            ),
            event_id=wake_event_id(run.id, run.wake_sequence),
        )
