"""Tests for immutable agent profile Markdown parsing."""

import pytest

from app.infrastructure.memory.agent_profile_markdown import (
    AgentProfileMarkdownError,
    parse_agent_profile_markdown,
)


def test_plain_agent_profile_has_no_metadata() -> None:
    document = parse_agent_profile_markdown("# Soul\n", location="SOUL.md")

    assert document.metadata == {}
    assert document.body == "# Soul\n"


def test_agent_profile_parses_only_explicit_metadata() -> None:
    document = parse_agent_profile_markdown(
        "---\ndisplay_label: Test profile\n---\n\n# Personal\n",
        location="PERSONAL.md",
    )

    assert document.metadata == {"display_label": "Test profile"}
    assert document.body == "\n# Personal\n"


@pytest.mark.parametrize(
    "text, expected_message",
    [
        ("---\nlabel: missing", "missing YAML front matter terminator"),
        ("---\n[invalid\n---\n", "invalid YAML front matter"),
        ("---\n- item\n---\n", "expected YAML mapping"),
    ],
)
def test_agent_profile_rejects_malformed_metadata(
    text: str,
    expected_message: str,
) -> None:
    with pytest.raises(AgentProfileMarkdownError, match=expected_message):
        parse_agent_profile_markdown(text, location="PERSONAL.md")
