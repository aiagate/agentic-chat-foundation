"""Observed Mediator wrapper that publishes application error events."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, is_dataclass
from typing import Any, cast

from flow_med import Mediator
from flow_res import AwaitableResult, is_err

from app.contracts.messages.app_error import (
    APP_ERROR_DETECTED_TOPIC,
    build_app_error_detected_payload,
)
from app.contracts.ports.event_bus import IEventBus

logger = logging.getLogger(__name__)

_event_bus: IEventBus | None = None
_original_send_async: Callable[[Any], Awaitable[Any]] | None = None
_installed = False


def install(event_bus: IEventBus) -> None:
    """Install the observed Mediator wrapper for the current process."""

    global _event_bus, _installed, _original_send_async

    _event_bus = event_bus
    if _installed:
        return

    _original_send_async = Mediator.send_async

    def _observed_send_async(
        _cls: type[Mediator],
        request: Any,
    ) -> AwaitableResult[Any, Any]:
        original_send_async = _original_send_async
        assert original_send_async is not None

        async def _observe() -> Any:
            try:
                result = await original_send_async(request)
            except Exception as exc:
                await _publish_error(request, exc, status="exception")
                raise

            if is_err(result):
                await _publish_error(request, result.error, status="error")
            return result

        return AwaitableResult(_observe())

    Mediator.send_async = classmethod(_observed_send_async)  # type: ignore[assignment]
    _installed = True


def reset() -> None:
    """Restore the original Mediator implementation."""

    global _event_bus, _installed, _original_send_async

    _event_bus = None
    if _installed and _original_send_async is not None:
        Mediator.send_async = _original_send_async  # type: ignore[assignment]
    _installed = False


async def _publish_error(request: Any, error: Any, *, status: str) -> None:
    if _event_bus is None:
        logger.warning("Mediator error observed without an event bus: %s", error)
        return

    payload = _build_payload(request, error, status=status)
    try:
        await _event_bus.publish(APP_ERROR_DETECTED_TOPIC, payload)
    except Exception:
        logger.exception("Failed to publish application error event")


def _build_payload(request: Any, error: Any, *, status: str) -> Mapping[str, object]:
    request_type = request.__class__.__name__
    operation_type = _operation_type(request_type)
    error_type, error_code, message, retryable = _error_details(error)
    request_fields = _request_fields(request)
    agent_context = cast(
        dict[str, object] | None, request_fields.pop("agent_context", None)
    )
    tool_call = cast(dict[str, object] | None, request_fields.pop("tool_call", None))
    event_fields = _event_fields(agent_context, tool_call)

    return build_app_error_detected_payload(
        layer="usecase",
        operation=request_type,
        operation_type=operation_type,
        status=status,
        error_type=error_type,
        error_code=error_code,
        message=message,
        retryable=retryable,
        request_type=request_type,
        chat_type=cast(str | None, request_fields.get("chat_type")),
        chat_id=cast(str | None, request_fields.get("chat_id")),
        user_id=cast(str | None, request_fields.get("user_id")),
        guild_id=cast(str | None, request_fields.get("guild_id")),
        channel_id=cast(str | None, request_fields.get("channel_id")),
        source_request_id=cast(str | None, request_fields.get("source_request_id")),
        tool_name=cast(str | None, request_fields.get("tool_name")),
        event_id=cast(str | None, event_fields.get("event_id")),
        correlation_id=cast(str | None, event_fields.get("correlation_id")),
        causation_id=cast(str | None, event_fields.get("causation_id")),
        agent_run_id=cast(str | None, event_fields.get("agent_run_id")),
        agent_turn_id=cast(str | None, event_fields.get("agent_turn_id")),
        tool_call_id=cast(str | None, event_fields.get("tool_call_id")),
        source_message_id=cast(str | None, event_fields.get("source_message_id")),
        decision_summary=cast(str | None, event_fields.get("decision_summary")),
    )


def _operation_type(request_type: str) -> str:
    if request_type.endswith("Query"):
        return "query"
    if request_type.endswith("Command"):
        return "command"
    return "request"


def _error_details(error: Any) -> tuple[str, str, str, bool]:
    error_type = error.__class__.__name__
    message = str(error)
    retryable = False
    error_code = error_type.lower()

    if hasattr(error, "type") and hasattr(error, "message"):
        error_type = "usecase_error"
        error_code = str(getattr(error.type, "name", error_code)).lower()
        message = str(getattr(error, "message", message))
        retryable = error_code in {"unexpected", "concurrency_conflict"}

    return error_type, error_code, message, retryable


def _request_fields(request: Any) -> dict[str, object]:
    raw: dict[str, object] = {}
    if is_dataclass(request):
        raw.update(asdict(cast(Any, request)))
    elif hasattr(request, "__dict__"):
        raw.update(
            {
                key: value
                for key, value in vars(request).items()
                if not key.startswith("_")
            }
        )

    selected: dict[str, object] = {}
    for key in (
        "chat_type",
        "chat_id",
        "user_id",
        "guild_id",
        "channel_id",
        "source_request_id",
        "tool_name",
    ):
        value = raw.get(key)
        normalized = _normalize_value(value)
        if normalized is not None:
            selected[key] = normalized

    agent_context = raw.get("agent_context")
    if agent_context is not None:
        selected["agent_context"] = agent_context
    tool_call = raw.get("tool_call")
    if tool_call is not None:
        selected["tool_call"] = tool_call
        if isinstance(tool_call, dict):
            tool_name = _normalize_value(tool_call.get("tool_name"))
            if tool_name is not None and "tool_name" not in selected:
                selected["tool_name"] = tool_name

    return selected


def _event_fields(
    agent_context: dict[str, object] | None,
    tool_call: dict[str, object] | None,
) -> dict[str, object]:
    fields: dict[str, object] = {}
    for source in (agent_context, tool_call):
        if not isinstance(source, dict):
            continue
        for key in (
            "event_id",
            "correlation_id",
            "causation_id",
            "agent_run_id",
            "agent_turn_id",
            "tool_call_id",
            "source_message_id",
            "decision_summary",
        ):
            value = source.get(key)
            normalized = _normalize_value(value)
            if normalized is not None and key not in fields:
                fields[key] = normalized
    return fields


def _normalize_value(value: object) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        return text if text else None
    if value is None:
        return None
    if hasattr(value, "to_primitive"):
        try:
            primitive = cast(Any, value).to_primitive()
            if isinstance(primitive, str):
                return primitive
        except Exception:
            return None
    return str(value)
