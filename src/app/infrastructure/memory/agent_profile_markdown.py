"""Markdown parsing for immutable agent profile configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import yaml

_FRONT_MATTER_BOUNDARY = "---"


class AgentProfileMarkdownError(ValueError):
    """Raised when agent profile metadata is malformed."""


@dataclass(frozen=True, slots=True)
class AgentProfileMarkdownDocument:
    """Agent profile Markdown body with optional configuration metadata."""

    metadata: dict[str, object]
    body: str


def parse_agent_profile_markdown(
    text: str,
    *,
    location: str,
) -> AgentProfileMarkdownDocument:
    """Parse optional YAML metadata without applying the memory document schema."""

    if not text.startswith(f"{_FRONT_MATTER_BOUNDARY}\n"):
        return AgentProfileMarkdownDocument(metadata={}, body=text)

    remainder = text[len(_FRONT_MATTER_BOUNDARY) + 1 :]
    terminator = f"\n{_FRONT_MATTER_BOUNDARY}\n"
    terminator_index = remainder.find(terminator)
    if terminator_index == -1:
        raise AgentProfileMarkdownError(
            f"{location}: missing YAML front matter terminator"
        )

    yaml_text = remainder[:terminator_index]
    try:
        loaded = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError as exc:
        raise AgentProfileMarkdownError(
            f"{location}: invalid YAML front matter"
        ) from exc
    if not isinstance(loaded, dict):
        raise AgentProfileMarkdownError(
            f"{location}: expected YAML mapping in front matter"
        )
    return AgentProfileMarkdownDocument(
        metadata=cast(dict[str, object], loaded),
        body=remainder[terminator_index + len(terminator) :],
    )
