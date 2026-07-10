"""SQLAlchemy persistence for the durable AgentRun state machine."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from flow_res import Err, Ok, Result
from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col
from ulid import ULID

from app.contracts.messages.agent_run import (
    AgentRunRecoveryResult,
    AgentRunSnapshot,
    AgentRunStatus,
    AgentToolCallSnapshot,
    AgentToolCallStatus,
    StartAgentRunResult,
)
from app.contracts.messages.chat_type import ChatType
from app.contracts.messages.tool_contracts import ToolCall, ToolContinuation
from app.contracts.ports.agent_run_repository import (
    AgentRunRepositoryError,
    IAgentRunRepository,
)
from app.infrastructure.orm_models.agent_run_orm import (
    AgentRunORM,
    AgentToolCallORM,
    ConversationCoordinatorORM,
)

_TERMINAL_TOOL_STATUSES = {
    AgentToolCallStatus.SUCCEEDED.value,
    AgentToolCallStatus.FAILED.value,
}


class AgentRunRepository(IAgentRunRepository):
    """Conditionally mutate workflow rows in the caller's transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def start(
        self,
        *,
        conversation_key: str,
        source_chat_id: str,
        character_id: str,
        user_id: str,
        chat_type: ChatType,
        guild_id: str,
        channel_id: str,
        max_turns: int,
    ) -> Result[StartAgentRunResult, AgentRunRepositoryError]:
        try:
            existing = await self._run_by_source_chat(source_chat_id)
            if existing is not None:
                return Ok(
                    StartAgentRunResult(
                        run=await self._snapshot(existing),
                        created=False,
                        should_wake=False,
                    )
                )

            await self._ensure_coordinator(conversation_key)
            coordinator = await self._coordinator(conversation_key, lock=True)
            if coordinator is None:
                return Err(AgentRunRepositoryError("Coordinator creation failed"))
            existing = await self._run_by_source_chat(source_chat_id)
            if existing is not None:
                return Ok(
                    StartAgentRunResult(
                        run=await self._snapshot(existing),
                        created=False,
                        should_wake=False,
                    )
                )

            ready = coordinator.active_run_id is None
            run = AgentRunORM(
                id=str(ULID()),
                conversation_key=conversation_key,
                source_chat_id=source_chat_id,
                character_id=character_id,
                user_id=user_id,
                chat_type=chat_type.value,
                guild_id=guild_id,
                channel_id=channel_id,
                status=(
                    AgentRunStatus.READY.value if ready else AgentRunStatus.QUEUED.value
                ),
                max_turns=max_turns,
                wake_sequence=1 if ready else 0,
            )
            self._session.add(run)
            if ready:
                coordinator.active_run_id = run.id
            coordinator.version += 1
            coordinator.updated_at = datetime.now().astimezone()
            await self._session.flush()
            return Ok(
                StartAgentRunResult(
                    run=await self._snapshot(run),
                    created=True,
                    should_wake=ready,
                )
            )
        except SQLAlchemyError as error:
            return Err(AgentRunRepositoryError(str(error)))

    async def claim_run(
        self,
        *,
        run_id: str,
        wake_sequence: int,
        now: datetime,
        lease_expires_at: datetime,
    ) -> Result[AgentRunSnapshot | None, AgentRunRepositoryError]:
        try:
            run = await self._run(run_id, lock=True)
            if run is None or run.wake_sequence != wake_sequence:
                return Ok(None)
            claimable = run.status == AgentRunStatus.READY.value or (
                run.status == AgentRunStatus.RUNNING.value
                and run.lease_expires_at is not None
                and self._is_due(run.lease_expires_at, now)
            )
            if not claimable or run.turn_number >= run.max_turns:
                return Ok(None)
            run.status = AgentRunStatus.RUNNING.value
            run.turn_number += 1
            run.attempt_count += 1
            run.lease_token = str(uuid4())
            run.lease_expires_at = lease_expires_at
            run.next_attempt_at = None
            run.version += 1
            run.updated_at = now
            await self._session.flush()
            return Ok(await self._snapshot(run, include_terminal_tools=True))
        except SQLAlchemyError as error:
            return Err(AgentRunRepositoryError(str(error)))

    async def add_tool_calls(
        self,
        *,
        run_id: str,
        lease_token: str,
        tool_calls: list[tuple[ToolCall, ToolContinuation]],
        now: datetime,
    ) -> Result[list[AgentToolCallSnapshot], AgentRunRepositoryError]:
        try:
            run = await self._run(run_id, lock=True)
            if run is None or not self._owns_running_run(run, lease_token):
                return Err(AgentRunRepositoryError("AgentRun lease was lost"))
            snapshots: list[AgentToolCallSnapshot] = []
            for tool_call, continuation in tool_calls:
                call_id = tool_call.tool_call_id or str(uuid4())
                durable_call = tool_call.model_copy(
                    update={
                        "tool_call_id": call_id,
                        "agent_run_id": run_id,
                        "agent_turn_id": str(run.turn_number),
                    }
                )
                row = AgentToolCallORM(
                    id=call_id,
                    agent_run_id=run_id,
                    turn_number=run.turn_number,
                    tool_name=durable_call.tool_name,
                    arguments=durable_call.arguments,
                    envelope=durable_call.model_dump(
                        mode="json", exclude={"arguments"}
                    ),
                    status=AgentToolCallStatus.PENDING.value,
                    continuation=continuation,
                )
                self._session.add(row)
                snapshots.append(self._tool_snapshot(row))
            run.status = AgentRunStatus.WAITING_FOR_TOOLS.value
            self._clear_run_lease(run)
            run.version += 1
            run.updated_at = now
            await self._session.flush()
            return Ok(snapshots)
        except SQLAlchemyError as error:
            return Err(AgentRunRepositoryError(str(error)))

    async def complete_run(
        self,
        *,
        run_id: str,
        lease_token: str,
        now: datetime,
    ) -> Result[AgentRunSnapshot | None, AgentRunRepositoryError]:
        try:
            run = await self._run(run_id, lock=True)
            if run is None or not self._owns_running_run(run, lease_token):
                return Err(AgentRunRepositoryError("AgentRun lease was lost"))
            return Ok(await self._finish_and_promote(run, now))
        except SQLAlchemyError as error:
            return Err(AgentRunRepositoryError(str(error)))

    async def defer_run(
        self,
        *,
        run_id: str,
        lease_token: str,
        error_code: str,
        error_message: str,
        next_attempt_at: datetime | None,
        now: datetime,
    ) -> Result[AgentRunSnapshot | None, AgentRunRepositoryError]:
        try:
            run = await self._run(run_id, lock=True)
            if run is None or not self._owns_running_run(run, lease_token):
                return Err(AgentRunRepositoryError("AgentRun lease was lost"))
            run.status = (
                AgentRunStatus.RETRY_WAIT.value
                if next_attempt_at is not None
                else AgentRunStatus.FAILED.value
            )
            run.next_attempt_at = next_attempt_at
            run.last_error_code = error_code
            run.last_error_message = error_message
            self._clear_run_lease(run)
            run.version += 1
            run.updated_at = now
            promoted = None
            if next_attempt_at is None:
                promoted = await self._release_and_promote(run, now)
            await self._session.flush()
            return Ok(promoted)
        except SQLAlchemyError as error:
            return Err(AgentRunRepositoryError(str(error)))

    async def claim_tool_call(
        self,
        *,
        run_id: str,
        tool_call_id: str,
        attempt_count: int,
        now: datetime,
        lease_expires_at: datetime,
    ) -> Result[
        tuple[AgentRunSnapshot, AgentToolCallSnapshot] | None, AgentRunRepositoryError
    ]:
        try:
            run = await self._run(run_id, lock=True)
            tool = await self._tool(tool_call_id, lock=True)
            if (
                run is None
                or tool is None
                or tool.agent_run_id != run_id
                or tool.attempt_count != attempt_count
                or run.status != AgentRunStatus.WAITING_FOR_TOOLS.value
            ):
                return Ok(None)
            claimable = tool.status == AgentToolCallStatus.PENDING.value or (
                tool.status == AgentToolCallStatus.RUNNING.value
                and tool.lease_expires_at is not None
                and self._is_due(tool.lease_expires_at, now)
            )
            if not claimable:
                return Ok(None)
            tool.status = AgentToolCallStatus.RUNNING.value
            tool.attempt_count += 1
            tool.lease_token = str(uuid4())
            tool.lease_expires_at = lease_expires_at
            tool.updated_at = now
            await self._session.flush()
            return Ok((await self._snapshot(run), self._tool_snapshot(tool)))
        except SQLAlchemyError as error:
            return Err(AgentRunRepositoryError(str(error)))

    async def complete_tool_call(
        self,
        *,
        run_id: str,
        tool_call_id: str,
        lease_token: str,
        succeeded: bool,
        result: dict[str, object],
        rendered_result: str,
        error_code: str | None,
        error_message: str | None,
        now: datetime,
    ) -> Result[AgentRunSnapshot | None, AgentRunRepositoryError]:
        try:
            run = await self._run(run_id, lock=True)
            tool = await self._tool(tool_call_id, lock=True)
            if (
                run is None
                or tool is None
                or tool.agent_run_id != run_id
                or tool.status != AgentToolCallStatus.RUNNING.value
                or tool.lease_token != lease_token
            ):
                return Err(AgentRunRepositoryError("AgentToolCall lease was lost"))
            tool.status = (
                AgentToolCallStatus.SUCCEEDED.value
                if succeeded
                else AgentToolCallStatus.FAILED.value
            )
            tool.result = result
            tool.rendered_result = rendered_result
            tool.error_code = error_code
            tool.error_message = error_message
            tool.lease_token = None
            tool.lease_expires_at = None
            tool.completed_at = now
            tool.updated_at = now
            await self._session.flush()

            if tool.continuation == "terminal":
                return Ok(await self._finish_waiting_and_promote(run, now))
            outstanding = await self._session.scalar(
                select(col(AgentToolCallORM.id))
                .where(
                    col(AgentToolCallORM.agent_run_id) == run_id,
                    col(AgentToolCallORM.turn_number) == tool.turn_number,
                    col(AgentToolCallORM.status).not_in(_TERMINAL_TOOL_STATUSES),
                )
                .limit(1)
            )
            if outstanding is not None:
                return Ok(None)
            if run.turn_number >= run.max_turns:
                run.status = AgentRunStatus.FAILED.value
                run.last_error_code = "max_turns_exceeded"
                run.last_error_message = "AgentRun reached its configured turn limit"
                run.version += 1
                run.updated_at = now
                return Ok(await self._release_and_promote(run, now))
            run.status = AgentRunStatus.READY.value
            run.wake_sequence += 1
            run.version += 1
            run.updated_at = now
            await self._session.flush()
            return Ok(await self._snapshot(run, include_terminal_tools=True))
        except SQLAlchemyError as error:
            return Err(AgentRunRepositoryError(str(error)))

    async def recover_due(
        self,
        *,
        now: datetime,
        limit: int,
    ) -> Result[AgentRunRecoveryResult, AgentRunRepositoryError]:
        try:
            run_rows = list(
                (
                    await self._session.scalars(
                        select(AgentRunORM)
                        .where(
                            or_(
                                and_(
                                    col(AgentRunORM.status)
                                    == AgentRunStatus.RUNNING.value,
                                    col(AgentRunORM.lease_expires_at) <= now,
                                ),
                                and_(
                                    col(AgentRunORM.status)
                                    == AgentRunStatus.RETRY_WAIT.value,
                                    col(AgentRunORM.next_attempt_at) <= now,
                                ),
                            )
                        )
                        .order_by(col(AgentRunORM.updated_at))
                        .limit(limit)
                        .with_for_update(skip_locked=True)
                    )
                ).all()
            )
            runs: list[AgentRunSnapshot] = []
            for run in run_rows:
                run.status = AgentRunStatus.READY.value
                run.wake_sequence += 1
                self._clear_run_lease(run)
                run.next_attempt_at = None
                run.version += 1
                run.updated_at = now
                runs.append(await self._snapshot(run, include_terminal_tools=True))

            remaining = max(limit - len(runs), 0)
            tool_rows: list[AgentToolCallORM] = []
            if remaining:
                tool_rows = list(
                    (
                        await self._session.scalars(
                            select(AgentToolCallORM)
                            .where(
                                col(AgentToolCallORM.status)
                                == AgentToolCallStatus.RUNNING.value,
                                col(AgentToolCallORM.lease_expires_at) <= now,
                            )
                            .order_by(col(AgentToolCallORM.updated_at))
                            .limit(remaining)
                            .with_for_update(skip_locked=True)
                        )
                    ).all()
                )
            tools: list[AgentToolCallSnapshot] = []
            for tool in tool_rows:
                tool.status = AgentToolCallStatus.PENDING.value
                tool.lease_token = None
                tool.lease_expires_at = None
                tool.updated_at = now
                tools.append(self._tool_snapshot(tool))
            await self._session.flush()
            return Ok(AgentRunRecoveryResult(runs=runs, tool_calls=tools))
        except SQLAlchemyError as error:
            return Err(AgentRunRepositoryError(str(error)))

    async def _coordinator(
        self, conversation_key: str, *, lock: bool = False
    ) -> ConversationCoordinatorORM | None:
        statement = select(ConversationCoordinatorORM).where(
            col(ConversationCoordinatorORM.conversation_key) == conversation_key
        )
        if lock:
            statement = statement.with_for_update()
        return await self._session.scalar(statement)

    async def _ensure_coordinator(self, conversation_key: str) -> None:
        """Create the mailbox row without racing another first message."""
        bind = self._session.get_bind()
        values = {"conversation_key": conversation_key, "version": 0}
        if bind.dialect.name == "postgresql":
            statement = postgresql_insert(ConversationCoordinatorORM).values(**values)
        else:
            statement = sqlite_insert(ConversationCoordinatorORM).values(**values)
        await self._session.execute(
            statement.on_conflict_do_nothing(index_elements=["conversation_key"])
        )

    async def _run(self, run_id: str, *, lock: bool = False) -> AgentRunORM | None:
        statement = select(AgentRunORM).where(col(AgentRunORM.id) == run_id)
        if lock:
            statement = statement.with_for_update()
        return await self._session.scalar(statement)

    async def _run_by_source_chat(self, source_chat_id: str) -> AgentRunORM | None:
        return await self._session.scalar(
            select(AgentRunORM).where(col(AgentRunORM.source_chat_id) == source_chat_id)
        )

    async def _tool(
        self, tool_call_id: str, *, lock: bool = False
    ) -> AgentToolCallORM | None:
        statement = select(AgentToolCallORM).where(
            col(AgentToolCallORM.id) == tool_call_id
        )
        if lock:
            statement = statement.with_for_update()
        return await self._session.scalar(statement)

    async def _snapshot(
        self, run: AgentRunORM, *, include_terminal_tools: bool = False
    ) -> AgentRunSnapshot:
        tools: list[AgentToolCallSnapshot] = []
        if include_terminal_tools:
            rows = (
                await self._session.scalars(
                    select(AgentToolCallORM)
                    .where(
                        col(AgentToolCallORM.agent_run_id) == run.id,
                        col(AgentToolCallORM.turn_number) == run.turn_number - 1,
                        col(AgentToolCallORM.status).in_(_TERMINAL_TOOL_STATUSES),
                    )
                    .order_by(
                        col(AgentToolCallORM.turn_number),
                        col(AgentToolCallORM.created_at),
                    )
                )
            ).all()
            tools = [self._tool_snapshot(row) for row in rows]
        return AgentRunSnapshot(
            id=run.id,
            conversation_key=run.conversation_key,
            source_chat_id=run.source_chat_id,
            character_id=run.character_id,
            user_id=run.user_id,
            chat_type=ChatType(run.chat_type),
            guild_id=run.guild_id,
            channel_id=run.channel_id,
            status=AgentRunStatus(run.status),
            turn_number=run.turn_number,
            max_turns=run.max_turns,
            attempt_count=run.attempt_count,
            next_attempt_at=run.next_attempt_at,
            lease_token=run.lease_token,
            lease_expires_at=run.lease_expires_at,
            wake_sequence=run.wake_sequence,
            version=run.version,
            last_error_code=run.last_error_code,
            last_error_message=run.last_error_message,
            tool_calls=tools,
        )

    @staticmethod
    def _tool_snapshot(row: AgentToolCallORM) -> AgentToolCallSnapshot:
        payload = dict(row.envelope)
        payload.update(tool_name=row.tool_name, arguments=dict(row.arguments))
        return AgentToolCallSnapshot(
            id=row.id,
            agent_run_id=row.agent_run_id,
            turn_number=row.turn_number,
            tool_call=ToolCall.model_validate(payload),
            status=AgentToolCallStatus(row.status),
            continuation=row.continuation,  # type: ignore[arg-type]
            attempt_count=row.attempt_count,
            result=dict(row.result or {}),
            rendered_result=row.rendered_result,
            error_code=row.error_code,
            error_message=row.error_message,
            lease_token=row.lease_token,
            lease_expires_at=row.lease_expires_at,
        )

    @staticmethod
    def _owns_running_run(run: AgentRunORM | None, lease_token: str) -> bool:
        return (
            run is not None
            and run.status == AgentRunStatus.RUNNING.value
            and run.lease_token == lease_token
        )

    @staticmethod
    def _clear_run_lease(run: AgentRunORM) -> None:
        run.lease_token = None
        run.lease_expires_at = None

    @staticmethod
    def _is_due(value: datetime, now: datetime) -> bool:
        """Compare database datetimes consistently across PostgreSQL and SQLite."""
        normalized_value = (
            value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        )
        normalized_now = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
        return normalized_value <= normalized_now

    async def _finish_and_promote(
        self, run: AgentRunORM, now: datetime
    ) -> AgentRunSnapshot | None:
        run.status = AgentRunStatus.COMPLETED.value
        run.completed_at = now
        self._clear_run_lease(run)
        run.version += 1
        run.updated_at = now
        return await self._release_and_promote(run, now)

    async def _finish_waiting_and_promote(
        self, run: AgentRunORM, now: datetime
    ) -> AgentRunSnapshot | None:
        run.status = AgentRunStatus.COMPLETED.value
        run.completed_at = now
        run.version += 1
        run.updated_at = now
        return await self._release_and_promote(run, now)

    async def _release_and_promote(
        self, run: AgentRunORM, now: datetime
    ) -> AgentRunSnapshot | None:
        coordinator = await self._coordinator(run.conversation_key, lock=True)
        if coordinator is None or coordinator.active_run_id != run.id:
            await self._session.flush()
            return None
        next_run = await self._session.scalar(
            select(AgentRunORM)
            .where(
                col(AgentRunORM.conversation_key) == run.conversation_key,
                col(AgentRunORM.status) == AgentRunStatus.QUEUED.value,
            )
            .order_by(col(AgentRunORM.created_at), col(AgentRunORM.id))
            .limit(1)
            .with_for_update()
        )
        coordinator.active_run_id = next_run.id if next_run is not None else None
        coordinator.version += 1
        coordinator.updated_at = now
        if next_run is None:
            await self._session.flush()
            return None
        next_run.status = AgentRunStatus.READY.value
        next_run.wake_sequence += 1
        next_run.version += 1
        next_run.updated_at = now
        await self._session.flush()
        return await self._snapshot(next_run)
