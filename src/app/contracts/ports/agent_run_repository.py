"""Persistence contract for durable AgentRun application state."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from flow_res import Result

from app.contracts.messages.agent_run import (
    AgentRunRecoveryResult,
    AgentRunSnapshot,
    AgentToolCallSnapshot,
    StartAgentRunResult,
)
from app.contracts.messages.chat_type import ChatType
from app.contracts.messages.tool_contracts import ToolCall, ToolContinuation


@dataclass(frozen=True, slots=True)
class AgentRunRepositoryError(Exception):
    """Failure while reading or conditionally changing workflow state."""

    message: str


class IAgentRunRepository(ABC):
    """Persist workflow state inside the caller's active transaction."""

    @abstractmethod
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
        raise NotImplementedError

    @abstractmethod
    async def claim_run(
        self,
        *,
        run_id: str,
        wake_sequence: int,
        now: datetime,
        lease_expires_at: datetime,
    ) -> Result[AgentRunSnapshot | None, AgentRunRepositoryError]:
        raise NotImplementedError

    @abstractmethod
    async def add_tool_calls(
        self,
        *,
        run_id: str,
        lease_token: str,
        tool_calls: list[tuple[ToolCall, ToolContinuation]],
        now: datetime,
    ) -> Result[list[AgentToolCallSnapshot], AgentRunRepositoryError]:
        raise NotImplementedError

    @abstractmethod
    async def complete_run(
        self,
        *,
        run_id: str,
        lease_token: str,
        now: datetime,
    ) -> Result[AgentRunSnapshot | None, AgentRunRepositoryError]:
        """Complete a run and return the next promoted run, if any."""

        raise NotImplementedError

    @abstractmethod
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
        raise NotImplementedError

    @abstractmethod
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
        raise NotImplementedError

    @abstractmethod
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
        """Persist a result and return a run that became ready or was promoted."""

        raise NotImplementedError

    @abstractmethod
    async def recover_due(
        self,
        *,
        now: datetime,
        limit: int,
    ) -> Result[AgentRunRecoveryResult, AgentRunRepositoryError]:
        raise NotImplementedError
