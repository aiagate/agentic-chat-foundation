"""Generated content message DTOs."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import ConfigDict, Field, model_validator

from app.contracts.messages.agentic import AgentEnvelope
from app.contracts.messages.tool_contracts import ToolCall


class GeneratedContent(AgentEnvelope):
    """Structured AI output for chat generation."""

    model_config = ConfigDict(extra="forbid")

    contents: list[str] = Field(
        default_factory=list,
        description="Generated assistant response texts.",
    )
    tool_calls: list[ToolCall] = Field(
        default_factory=list,
        description="Canonical tool calls requested by the model.",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_payload(cls, value: object) -> object:
        """Accept legacy tool-call-only payloads from the model."""

        if isinstance(value, list):
            if len(value) == 1 and isinstance(value[0], Mapping):
                first_item = value[0]
                if "tool_calls" in first_item or "contents" in first_item:
                    return _normalize_generated_content_mapping(first_item)
            normalized_tool_calls: list[dict[str, object]] = []
            for item in value:
                normalized_tool_call = _normalize_legacy_tool_call(item)
                if normalized_tool_call is None:
                    return value
                normalized_tool_calls.append(normalized_tool_call)
            return {"contents": [], "tool_calls": normalized_tool_calls}

        if isinstance(value, Mapping):
            return _normalize_generated_content_mapping(value)

        return value


def _normalize_legacy_tool_call(value: object) -> dict[str, object] | None:
    """Normalize an OpenAI-style tool call payload into the canonical schema."""

    if not isinstance(value, Mapping):
        return None

    raw_arguments = value.get("arguments")
    if not isinstance(raw_arguments, Mapping):
        return None

    tool_name = value.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name.strip():
        tool_name = value.get("name")
    if not isinstance(tool_name, str) or not tool_name.strip():
        return None

    normalized: dict[str, object] = {
        "tool_name": tool_name.strip(),
        "arguments": dict(raw_arguments),
    }

    tool_call_id = value.get("tool_call_id")
    if not isinstance(tool_call_id, str) or not tool_call_id.strip():
        tool_call_id = value.get("id")
    if isinstance(tool_call_id, str) and tool_call_id.strip():
        normalized["tool_call_id"] = tool_call_id.strip()

    for key in (
        "character_id",
        "source_message_id",
        "decision_summary",
    ):
        raw_value = value.get(key)
        if isinstance(raw_value, str) and raw_value.strip():
            normalized[key] = raw_value.strip()

    return normalized


def _normalize_contents_field(value: object) -> list[str] | None:
    """Normalize the contents field into a list of non-empty strings."""

    if isinstance(value, str):
        normalized = value.strip()
        return [normalized] if normalized else []

    if isinstance(value, list):
        normalized = [
            str(item).strip()
            for item in value
            if isinstance(item, str) and item.strip()
        ]
        return normalized

    if value is None:
        return None

    return None


def _normalize_generated_content_mapping(
    value: Mapping[str, object],
) -> dict[str, object] | object:
    normalized_contents = _normalize_contents_field(value.get("contents"))
    raw_tool_calls = value.get("tool_calls")
    normalized_value = dict(value)
    if normalized_contents is not None:
        normalized_value["contents"] = normalized_contents
    if isinstance(raw_tool_calls, list):
        normalized_tool_calls = []
        for item in raw_tool_calls:
            normalized_tool_call = _normalize_legacy_tool_call(item)
            if normalized_tool_call is None:
                return value
            normalized_tool_calls.append(normalized_tool_call)
        normalized_value["tool_calls"] = normalized_tool_calls
    elif "contents" not in normalized_value:
        normalized_value["contents"] = []
    return normalized_value
