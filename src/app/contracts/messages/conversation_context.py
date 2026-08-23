"""Conversation context DTOs shared across application layers."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConversationContext(BaseModel):
    """Structured metadata about the current chat session."""

    model_config = ConfigDict(extra="forbid")

    chat_scope: str = Field(description="Human-readable scope of the chat.")
    current_time: datetime = Field(description="Current reference time.")
    timezone: str = Field(description="Timezone name for the rendered time.")
    observed_message_count: int = Field(
        description="Number of history messages used for the current session window."
    )
    has_session_boundary: bool = Field(
        description="Whether a session boundary was detected in the observed window."
    )
    current_session_started_at: datetime | None = Field(
        default=None,
        description="Start time of the observed current session, if known.",
    )
    previous_message_at: datetime | None = Field(
        default=None,
        description="Timestamp immediately before the detected session boundary.",
    )
    gap_minutes: int | None = Field(
        default=None,
        description="Gap in minutes across the detected session boundary.",
    )


def render_conversation_context(context: ConversationContext) -> str:
    """Render structured conversation metadata for system instructions."""

    lines = [
        "Conversation Context:",
        f"- chat_scope: {context.chat_scope}",
        f"- current_time: {context.current_time.isoformat()}",
        f"- timezone: {context.timezone}",
        f"- observed_message_count: {context.observed_message_count}",
        f"- has_session_boundary: {str(context.has_session_boundary).lower()}",
        (
            "- current_session_started_at: "
            f"{_render_datetime(context.current_session_started_at)}"
        ),
        f"- previous_message_at: {_render_datetime(context.previous_message_at)}",
        f"- gap_minutes: {_render_optional_int(context.gap_minutes)}",
        "",
        "Rules:",
        "- Use timestamps only to interpret continuity and recency.",
        "- Do not copy timestamps into the reply.",
        (
            "- If has_session_boundary is true, do not assume the user's current "
            "state, plans, or meal status continue from earlier messages unless "
            "explicitly stated."
        ),
    ]
    return "\n".join(lines)


def _render_datetime(value: datetime | None) -> str:
    if value is None:
        return "null"
    return value.isoformat()


def _render_optional_int(value: int | None) -> str:
    if value is None:
        return "null"
    return str(value)
