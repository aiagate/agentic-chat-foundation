"""Tool catalog port."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.contracts.messages.tool_contracts import ToolDefinition


class IToolCatalog(ABC):
    """Resolve available tool definitions for an agent run."""

    @abstractmethod
    def list_tools(self) -> list[ToolDefinition]:
        """Return the tools available to the current runtime."""
        raise NotImplementedError

    @abstractmethod
    def get_tool(self, tool_name: str) -> ToolDefinition | None:
        """Return a single tool definition by name, if available."""
        raise NotImplementedError
