"""Port for assembling prompt-ready agent inference context."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from flow_res import Result

from app.contracts.messages.agent_turn_context import AgentTurnContext
from app.contracts.messages.chat_type import ChatType
from app.contracts.messages.llm_request_context import LLMRequestContext
from app.contracts.messages.tool_result_context import ToolResultContext


@dataclass(frozen=True, slots=True)
class AgentInferenceContextRequest:
    """Inputs required to assemble one LLM request context."""

    turn_context: AgentTurnContext
    message_id: str
    user_id: str
    character_id: str
    chat_type: ChatType
    tool_results: tuple[ToolResultContext, ...] = ()


@dataclass(frozen=True, slots=True)
class AgentInferenceContextError(Exception):
    """Failure while assembling an agent inference context."""

    message: str


class IAgentInferenceContextService(ABC):
    """Gather agent inputs and build a provider-independent LLM context."""

    @abstractmethod
    async def assemble(
        self,
        request: AgentInferenceContextRequest,
    ) -> Result[LLMRequestContext, AgentInferenceContextError]:
        """Assemble one prompt-ready LLM request context."""
