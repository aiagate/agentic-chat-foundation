"""Bind canonical application tools to provider-safe function names."""

from __future__ import annotations

import re
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

    bindings: list[ProviderToolBinding] = []
    used_aliases: set[str] = set()
    for definition in tool_definitions or []:
        base_alias = re.sub(r"[^A-Za-z0-9_]", "_", definition.name).strip("_")
        if not base_alias or base_alias[0].isdigit():
            base_alias = f"tool_{base_alias}" if base_alias else "tool"
        alias = base_alias
        suffix = 2
        while alias in used_aliases:
            alias = f"{base_alias}_{suffix}"
            suffix += 1
        used_aliases.add(alias)
        bindings.append(ProviderToolBinding(alias=alias, definition=definition))
    return bindings


def canonical_tool_name(
    provider_name: str,
    bindings: list[ProviderToolBinding],
) -> str | None:
    """Resolve one provider function name to its canonical application name."""

    for binding in bindings:
        if binding.alias == provider_name:
            return binding.definition.name
    return None
