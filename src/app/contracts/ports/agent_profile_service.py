"""Agent profile service port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.contracts.messages.agent_profile import AgentProfileBundle


@dataclass
class AgentProfileServiceError(Exception):
    """Represents an agent profile service failure."""

    message: str

    def __str__(self) -> str:
        return self.message


class IAgentProfileService(ABC):
    """Load the built-in agent profile bundle from storage."""

    @abstractmethod
    def ensure_agent_profile_bundle(self) -> None:
        """Validate that the agent profile bundle is present and readable."""

    @abstractmethod
    def load_agent_profile_bundle(self) -> AgentProfileBundle:
        """Return the parsed agent profile bundle."""
