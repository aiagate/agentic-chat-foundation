"""Durable application state for one agent workflow run."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.messages.chat_type import ChatType
from app.contracts.messages.tool_contracts import ToolCall, ToolContinuation
from app.contracts.messages.tool_result_context import ToolResultContext


class AgentRunStatus(StrEnum):
    """Persisted lifecycle of one accepted user-message run."""

    QUEUED = "queued"
    READY = "ready"
    RUNNING = "running"
    WAITING_FOR_TOOLS = "waiting_for_tools"
    RETRY_WAIT = "retry_wait"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentToolCallStatus(StrEnum):
    """Persisted lifecycle of one tool call."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AgentToolCallSnapshot(BaseModel):
    """Storage-independent view of one durable tool call."""

    model_config = ConfigDict(extra="forbid")

    id: str
    agent_run_id: str
    turn_number: int
    tool_call: ToolCall
    status: AgentToolCallStatus
    continuation: ToolContinuation
    attempt_count: int = 0
    result: dict[str, object] = Field(default_factory=dict)
    rendered_result: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    lease_token: str | None = None
    lease_expires_at: datetime | None = None

    def to_result_context(self, *, character_id: str) -> ToolResultContext | None:
        """Return prompt-ready context after execution has reached a terminal state."""

        if self.status not in {
            AgentToolCallStatus.SUCCEEDED,
            AgentToolCallStatus.FAILED,
        }:
            return None
        rendered = self.rendered_result or (
            f"{self.tool_call.tool_name} failed: {self.error_message or 'unknown error'}"
        )
        return ToolResultContext(
            tool_call_id=self.id,
            character_id=character_id,
            tool_name=self.tool_call.tool_name,
            status=("ok" if self.status is AgentToolCallStatus.SUCCEEDED else "error"),
            result=dict(self.result),
            error=self.error_message,
            rendered_text=rendered,
        )


class AgentRunSnapshot(BaseModel):
    """Storage-independent view used by application workflow components."""

    model_config = ConfigDict(extra="forbid")

    id: str
    conversation_key: str
    source_chat_id: str
    character_id: str
    user_id: str
    chat_type: ChatType
    guild_id: str
    channel_id: str
    status: AgentRunStatus
    turn_number: int
    max_turns: int
    attempt_count: int
    next_attempt_at: datetime | None = None
    lease_token: str | None = None
    lease_expires_at: datetime | None = None
    wake_sequence: int
    version: int
    last_error_code: str | None = None
    last_error_message: str | None = None
    tool_calls: list[AgentToolCallSnapshot] = Field(default_factory=list)

    @property
    def tool_results(self) -> list[ToolResultContext]:
        """Return all terminal tool results for the most recently completed turn."""

        contexts = [
            tool_call.to_result_context(character_id=self.character_id)
            for tool_call in self.tool_calls
        ]
        return [context for context in contexts if context is not None]


class StartAgentRunResult(BaseModel):
    """Result of idempotently accepting a chat into a conversation mailbox."""

    model_config = ConfigDict(extra="forbid")

    run: AgentRunSnapshot
    created: bool
    should_wake: bool


class AgentRunRecoveryResult(BaseModel):
    """Durable work made dispatchable again by a recovery scan."""

    model_config = ConfigDict(extra="forbid")

    runs: list[AgentRunSnapshot] = Field(default_factory=list)
    tool_calls: list[AgentToolCallSnapshot] = Field(default_factory=list)
