"""Static tool catalog for the agent runtime."""

from __future__ import annotations

from app.contracts.messages.tool_contracts import ToolDefinition
from app.contracts.ports.tool_catalog import IToolCatalog

_MESSAGE_CONTENTS_DESCRIPTION = (
    "Response texts divided into natural conversational message units. "
    "Each item is delivered as one separate message to the tool destination."
)


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
            "memory.write_candidate": ToolDefinition(
                name="memory.write_candidate",
                description="Record a candidate memory log for later consolidation.",
                arguments_schema={
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "role": {
                            "type": "string",
                            "enum": ["user", "assistant", "system"],
                        },
                        "metadata": {"type": "object"},
                    },
                    "required": ["content"],
                    "additionalProperties": False,
                },
                result_schema={
                    "type": "object",
                    "properties": {
                        "written": {"type": "boolean"},
                    },
                    "required": ["written"],
                    "additionalProperties": True,
                },
                capability_scope=["memory:write"],
                side_effect="write",
                timeout_seconds=20,
                max_calls_per_run=2,
            ),
            "line.send": ToolDefinition(
                name="line.send",
                description="Send messages to the current LINE conversation.",
                arguments_schema={
                    "type": "object",
                    "properties": {
                        "contents": {
                            "type": "array",
                            "description": _MESSAGE_CONTENTS_DESCRIPTION,
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["contents"],
                    "additionalProperties": False,
                },
                result_schema={
                    "type": "object",
                    "properties": {
                        "content_count": {"type": "integer"},
                    },
                    "required": ["content_count"],
                    "additionalProperties": True,
                },
                capability_scope=["message:send:line"],
                side_effect="send_message",
                timeout_seconds=15,
                max_calls_per_run=1,
            ),
            "discord.send": ToolDefinition(
                name="discord.send",
                description="Send messages to the current Discord channel.",
                arguments_schema={
                    "type": "object",
                    "properties": {
                        "contents": {
                            "type": "array",
                            "description": _MESSAGE_CONTENTS_DESCRIPTION,
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["contents"],
                    "additionalProperties": False,
                },
                result_schema={
                    "type": "object",
                    "properties": {
                        "content_count": {"type": "integer"},
                    },
                    "required": ["content_count"],
                    "additionalProperties": True,
                },
                capability_scope=["message:send:discord"],
                side_effect="send_message",
                timeout_seconds=15,
                max_calls_per_run=1,
            ),
        }

    def list_tools(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def get_tool(self, tool_name: str) -> ToolDefinition | None:
        return self._tools.get(tool_name)
