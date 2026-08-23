"""Static tool catalog for the agent runtime."""

from __future__ import annotations

from app.contracts.messages.tool_contracts import ToolDefinition
from app.contracts.ports.tool_catalog import IToolCatalog


class StaticToolCatalog(IToolCatalog):
    """Stable tool definitions surfaced to the agent runtime."""

    def __init__(self) -> None:
        self._tools = {
            "web_search": ToolDefinition(
                name="web_search",
                description="Search the public web for current information.",
                arguments_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "max_results": {"type": "integer", "minimum": 1},
                        "source_request_id": {"type": "string"},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                result_schema={
                    "type": "object",
                    "properties": {
                        "tool_call_id": {"type": "string"},
                        "retrieved_context": {"type": "boolean"},
                        "result_count": {"type": "integer"},
                    },
                    "required": ["tool_call_id", "retrieved_context", "result_count"],
                    "additionalProperties": True,
                },
                capability_scope=["search:web"],
                side_effect="read",
                timeout_seconds=30,
                max_calls_per_run=3,
            ),
            "memory.read": ToolDefinition(
                name="memory.read",
                description="Read one long-term memory item by memory_id.",
                arguments_schema={
                    "type": "object",
                    "properties": {
                        "memory_id": {"type": "string"},
                    },
                    "required": ["memory_id"],
                    "additionalProperties": False,
                },
                result_schema={
                    "type": "object",
                    "properties": {
                        "tool_call_id": {"type": "string"},
                        "retrieved_context": {"type": "boolean"},
                        "result_count": {"type": "integer"},
                    },
                    "required": ["tool_call_id", "retrieved_context", "result_count"],
                    "additionalProperties": True,
                },
                capability_scope=["memory:read"],
                side_effect="read",
                timeout_seconds=20,
                max_calls_per_run=4,
            ),
        }

    def list_tools(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def get_tool(self, tool_name: str) -> ToolDefinition | None:
        return self._tools.get(tool_name)
