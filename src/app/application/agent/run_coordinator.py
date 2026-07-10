"""Conversation-scoped durable AgentRun coordinator."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from flow_res import Err, Ok, Result, is_err

from app.application.agent.reply_persistence import AgentReplyPersistence
from app.application.agent.turn_runner import AgentTurnRunner
from app.contracts.messages.agent_run import AgentRunSnapshot
from app.contracts.messages.agent_run_events import (
    AGENT_RUN_WAKEUP_TOPIC,
    AGENT_TOOL_REQUESTED_TOPIC,
    build_agent_run_wakeup_payload,
    build_agent_tool_requested_payload,
    tool_request_event_id,
    wake_event_id,
)
from app.contracts.messages.tool_contracts import ToolCall, ToolContinuation
from app.contracts.ports.tool_catalog import IToolCatalog
from app.contracts.ports.unit_of_work import IUnitOfWork


@dataclass(frozen=True, slots=True)
class AgentWorkflowError(Exception):
    """Failure to advance durable workflow state."""

    message: str


class AgentRunCoordinator:
    """Advance a run through short lease/apply transactions."""

    def __init__(
        self,
        uow: IUnitOfWork,
        turn_runner: AgentTurnRunner,
        tool_catalog: IToolCatalog,
        reply_persistence: AgentReplyPersistence,
    ) -> None:
        self._uow = uow
        self._turn_runner = turn_runner
        self._tool_catalog = tool_catalog
        self._reply_persistence = reply_persistence

    async def advance(
        self, *, run_id: str, wake_sequence: int
    ) -> Result[bool, AgentWorkflowError]:
        now = datetime.now(UTC)
        async with self._uow:
            claim = await self._uow.GetAgentRunRepository().claim_run(
                run_id=run_id,
                wake_sequence=wake_sequence,
                now=now,
                lease_expires_at=now + timedelta(minutes=5),
            )
            if is_err(claim):
                return Err(AgentWorkflowError(claim.error.message))
            if claim.value is None:
                return Ok(False)
            commit = await self._uow.commit()
            if is_err(commit):
                return Err(AgentWorkflowError(commit.error.message))
            run = claim.value

        generated = await self._turn_runner.run(run)
        if is_err(generated):
            return await self._defer(run, generated.error.code, generated.error.message)

        validation_error = self._validate_tool_calls(
            run,
            generated.value.tool_calls,
            has_contents=bool(generated.value.contents),
        )
        if validation_error is not None:
            return await self._defer(run, "invalid_tool_plan", validation_error)

        now = datetime.now(UTC)
        async with self._uow:
            repository = self._uow.GetAgentRunRepository()
            if generated.value.contents:
                persisted = await self._reply_persistence.write(
                    run=run, contents=generated.value.contents
                )
                if is_err(persisted):
                    return Err(AgentWorkflowError(persisted.error.message))

            if generated.value.tool_calls:
                durable_calls = await repository.add_tool_calls(
                    run_id=run.id,
                    lease_token=run.lease_token or "",
                    tool_calls=[
                        (tool_call, self._continuation(tool_call))
                        for tool_call in generated.value.tool_calls
                    ],
                    now=now,
                )
                if is_err(durable_calls):
                    return Err(AgentWorkflowError(durable_calls.error.message))
                for tool in durable_calls.value:
                    self._uow.enqueue_event(
                        AGENT_TOOL_REQUESTED_TOPIC,
                        build_agent_tool_requested_payload(
                            agent_run_id=run.id,
                            tool_call_id=tool.id,
                            attempt_count=tool.attempt_count,
                        ),
                        event_id=tool_request_event_id(tool.id, tool.attempt_count),
                    )
            else:
                completed = await repository.complete_run(
                    run_id=run.id,
                    lease_token=run.lease_token or "",
                    now=now,
                )
                if is_err(completed):
                    return Err(AgentWorkflowError(completed.error.message))
                if completed.value is not None:
                    self._enqueue_wakeup(completed.value)
            commit = await self._uow.commit()
            if is_err(commit):
                return Err(AgentWorkflowError(commit.error.message))
        return Ok(True)

    async def _defer(
        self, run: AgentRunSnapshot, code: str, message: str
    ) -> Result[bool, AgentWorkflowError]:
        now = datetime.now(UTC)
        retry_at = (
            now + timedelta(seconds=min(300, 2**run.attempt_count))
            if run.attempt_count < 3
            else None
        )
        async with self._uow:
            deferred = await self._uow.GetAgentRunRepository().defer_run(
                run_id=run.id,
                lease_token=run.lease_token or "",
                error_code=code,
                error_message=message,
                next_attempt_at=retry_at,
                now=now,
            )
            if is_err(deferred):
                return Err(AgentWorkflowError(deferred.error.message))
            if deferred.value is not None:
                self._enqueue_wakeup(deferred.value)
            commit = await self._uow.commit()
            if is_err(commit):
                return Err(AgentWorkflowError(commit.error.message))
        return Ok(True)

    def _validate_tool_calls(
        self,
        run: AgentRunSnapshot,
        calls: list[ToolCall],
        *,
        has_contents: bool,
    ) -> str | None:
        send_calls = 0
        counts: dict[str, int] = {}
        for call in calls:
            definition = self._tool_catalog.get_tool(call.tool_name)
            if definition is None:
                return f"Unknown tool: {call.tool_name}"
            if call.tool_name == "line.send" and run.chat_type.value != "LINE":
                return "line.send is only available for LINE chats"
            if call.tool_name == "discord.send" and run.chat_type.value != "DISCORD":
                return "discord.send is only available for Discord chats"
            counts[call.tool_name] = counts.get(call.tool_name, 0) + 1
            if (
                definition.max_calls_per_run is not None
                and counts[call.tool_name] > definition.max_calls_per_run
            ):
                return f"Tool call limit exceeded: {call.tool_name}"
            if definition.side_effect == "send_message":
                send_calls += 1
        if send_calls and (len(calls) != 1 or has_contents):
            return "A send_message tool must be the only output in a turn"
        return None

    def _continuation(self, call: ToolCall) -> ToolContinuation:
        definition = self._tool_catalog.get_tool(call.tool_name)
        return (
            "terminal"
            if definition is not None and definition.side_effect == "send_message"
            else "reenter"
        )

    def _enqueue_wakeup(self, run: AgentRunSnapshot) -> None:
        self._uow.enqueue_event(
            AGENT_RUN_WAKEUP_TOPIC,
            build_agent_run_wakeup_payload(
                agent_run_id=run.id, wake_sequence=run.wake_sequence
            ),
            event_id=wake_event_id(run.id, run.wake_sequence),
        )
