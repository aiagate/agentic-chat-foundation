"""Agent-turn context query boundary."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from flow_res import Result

from app.contracts.messages.agent_turn_context import AgentTurnContext
from app.contracts.messages.chat_type import ChatType


@dataclass
class AgentTurnContextQueryError(Exception):
    """Failure to resolve the persisted context for an agent turn."""

    message: str

    def __str__(self) -> str:
        return self.message


class IAgentTurnContextQuery(ABC):
    """Resolve all database-backed inputs for one agent turn."""

    @abstractmethod
    async def load(
        self,
        *,
        chat_id: str,
        provided_prompt: str | None,
        chat_type: ChatType,
        user_id: str,
        guild_id: str,
        channel_id: str,
    ) -> Result[AgentTurnContext, AgentTurnContextQueryError]:
        """Load a prompt and its active conversation window."""
        raise NotImplementedError
