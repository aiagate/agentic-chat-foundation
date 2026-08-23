"""Tests for the static agent tool catalog."""

from app.infrastructure.services.tool_catalog import StaticToolCatalog


def test_catalog_contains_only_executable_context_tools() -> None:
    catalog = StaticToolCatalog()

    assert {tool.name for tool in catalog.list_tools()} == {
        "web_search",
        "memory.read",
    }
    assert catalog.get_tool("line.send") is None
    assert catalog.get_tool("discord.send") is None
