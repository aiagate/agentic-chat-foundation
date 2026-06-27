"""Tests for the static agent tool catalog."""

from typing import cast

import pytest

from app.infrastructure.services.tool_catalog import StaticToolCatalog


@pytest.mark.parametrize(
    ("tool_name", "required_arguments"),
    [
        ("line.send", ["contents"]),
        ("discord.send", ["contents"]),
    ],
)
def test_send_message_tools_require_contents(
    tool_name: str,
    required_arguments: list[str],
) -> None:
    tool = StaticToolCatalog().get_tool(tool_name)

    assert tool is not None
    schema = tool.arguments_schema
    properties = cast(dict[str, object], schema["properties"])
    contents = cast(dict[str, object], properties["contents"])
    assert "content" not in properties
    assert schema["required"] == required_arguments
    assert contents["description"] == (
        "Response texts divided into natural conversational message units. "
        "Each item is delivered as one separate message to the tool destination."
    )
