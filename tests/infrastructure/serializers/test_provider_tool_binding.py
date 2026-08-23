"""Tests for provider-safe canonical tool bindings."""

from app.contracts.messages.tool_contracts import ToolDefinition
from app.infrastructure.serializers.provider_tool_binding import (
    bind_provider_tools,
    canonical_tool_name,
)


def test_bind_provider_tools_uses_safe_request_local_aliases() -> None:
    definitions = [
        ToolDefinition(name="memory.read", description="Read memory."),
        ToolDefinition(name="web.search", description="Search the web."),
    ]

    bindings = bind_provider_tools(definitions)

    assert [binding.alias for binding in bindings] == ["memory_read", "web_search"]
    assert canonical_tool_name("memory_read", bindings) == "memory.read"
    assert canonical_tool_name("web_search", bindings) == "web.search"
    assert canonical_tool_name("unknown", bindings) is None


def test_bind_provider_tools_resolves_normalized_name_collisions() -> None:
    definitions = [
        ToolDefinition(name="memory.read", description="Read memory."),
        ToolDefinition(name="memory-read", description="Read other memory."),
    ]

    bindings = bind_provider_tools(definitions)

    assert [binding.alias for binding in bindings] == ["memory_read", "memory_read_2"]
