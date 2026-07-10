"""Port for atomically persisting generated agent replies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from flow_res import Result

from app.contracts.messages.agentic import AgentEnvelope
from app.domain.value_objects.chat_type import ChatType


@dataclass(frozen=True, slots=True)
class AgentReplyWriteRequest:
    """Data required to persist and announce one generated reply."""

    chat_type: ChatType
    guild_id: str
    channel_id: str
    user_id: str
    contents: list[str]
    agent_context: AgentEnvelope


@dataclass(frozen=True, slots=True)
class AgentReplyWriteError(Exception):
    """Failure while persisting a generated reply."""

    message: str


class IAgentReplyWriter(ABC):
    """Persist generated replies and their delivery event atomically."""

    @abstractmethod
    async def write(
        self,
        request: AgentReplyWriteRequest,
    ) -> Result[None, AgentReplyWriteError]:
        """Persist one reply and enqueue its ready event."""
