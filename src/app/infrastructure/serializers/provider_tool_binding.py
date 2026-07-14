"""Bind canonical application tools to provider-safe function names."""

from __future__ import annotations

from dataclasses import dataclass

from app.contracts.messages.tool_contracts import ToolDefinition


@dataclass(frozen=True, slots=True)
class ProviderToolBinding:
    """One provider-safe alias associated with a canonical tool definition."""

    alias: str
    definition: ToolDefinition


def bind_provider_tools(
    tool_definitions: list[ToolDefinition] | None,
) -> list[ProviderToolBinding]:
    """Assign stable request-local aliases accepted by every target provider."""

    return [
        ProviderToolBinding(alias=f"tool_{index}", definition=definition)
        for index, definition in enumerate(tool_definitions or [])
    ]


def canonical_tool_name(
    provider_name: str,
    bindings: list[ProviderToolBinding],
) -> str | None:
    """Resolve one provider function name to its canonical application name."""

    for binding in bindings:
        if binding.alias == provider_name:
            return binding.definition.name
    return None
