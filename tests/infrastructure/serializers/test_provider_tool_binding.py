"""Tests for provider-safe canonical tool bindings."""

from app.contracts.messages.tool_contracts import ToolDefinition
from app.infrastructure.serializers.provider_tool_binding import (
    bind_provider_tools,
    canonical_tool_name,
)


def test_bind_provider_tools_uses_safe_request_local_aliases() -> None:
    definitions = [
        ToolDefinition(name="memory.read", description="Read memory."),
        ToolDefinition(name="line.send", description="Send a LINE reply."),
    ]

    bindings = bind_provider_tools(definitions)

    assert [binding.alias for binding in bindings] == ["tool_0", "tool_1"]
    assert canonical_tool_name("tool_0", bindings) == "memory.read"
    assert canonical_tool_name("tool_1", bindings) == "line.send"
    assert canonical_tool_name("unknown", bindings) is None
