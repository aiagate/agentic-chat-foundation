"""Helpers for logging AI request context."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any

from app.contracts.messages.chat_history import ChatHistoryItem
from app.contracts.messages.tool_contracts import ToolDefinition


def log_ai_request_context(
    logger: logging.Logger,
    *,
    service_name: str,
    payload: dict[str, Any],
) -> None:
    """Log the full request context that will be sent to the LLM."""

    logger.info(
        "%s request context: %s",
        service_name,
        json.dumps(payload, ensure_ascii=False, default=str),
    )


def serialize_history(history: Sequence[ChatHistoryItem]) -> list[dict[str, Any]]:
    """Convert history items into JSON-serializable dictionaries."""

    return [item.model_dump(mode="json") for item in history]


def serialize_tool_definitions(
    tool_definitions: Sequence[ToolDefinition] | None,
) -> list[dict[str, Any]] | None:
    """Convert tool definitions into JSON-serializable dictionaries."""

    if tool_definitions is None:
        return None
    return [tool.model_dump(mode="json") for tool in tool_definitions]
