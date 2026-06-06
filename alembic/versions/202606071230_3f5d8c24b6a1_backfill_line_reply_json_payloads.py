"""Backfill LINE reply JSON payloads into plain text.

Revision ID: 3f5d8c24b6a1
Revises: 202605301900
Create Date: 2026-06-07 12:30:00.000000

"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3f5d8c24b6a1"
down_revision: str | Sequence[str] | None = "202605301900"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Replace persisted tool-call JSON with the actual assistant text."""

    connection = op.get_bind()
    chats = sa.table(
        "chats",
        sa.column("id", sa.String(length=26)),
        sa.column("type", sa.String(length=20)),
        sa.column("role", sa.String(length=32)),
        sa.column("message_content", sa.JSON()),
    )

    rows = connection.execute(
        sa.select(chats.c.id, chats.c.message_content).where(
            chats.c.type == "LINE",
            chats.c.role == "assistant",
        )
    )

    for row in rows:
        message_content = _to_plain_message_content(row.message_content)
        if message_content is None:
            continue
        connection.execute(
            sa.update(chats)
            .where(chats.c.id == row.id)
            .values(message_content=message_content)
        )


def downgrade() -> None:
    """No safe downgrade exists for the normalized assistant text."""


def _to_plain_message_content(
    message_content: object,
) -> dict[str, object] | None:
    """Extract assistant prose from legacy serialized tool-call payloads."""

    if not isinstance(message_content, dict):
        return None

    payload = message_content.get("payload")
    if not isinstance(payload, dict):
        return None

    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        return None

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, list):
        return None

    rewritten = _extract_plain_text(parsed)
    if rewritten is None:
        return None

    updated_payload = dict(payload)
    updated_payload["text"] = rewritten
    updated_message_content = dict(message_content)
    updated_message_content["payload"] = updated_payload
    return updated_message_content


def _extract_plain_text(tool_calls: list[object]) -> str | None:
    """Collect human-facing text from legacy tool-call payloads."""

    texts: list[str] = []
    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            continue

        arguments = tool_call.get("arguments")
        if not isinstance(arguments, dict):
            continue

        content = arguments.get("content")
        if isinstance(content, str) and content.strip():
            texts.append(content.strip())
            continue

        contents = arguments.get("contents")
        if isinstance(contents, list):
            texts.extend(
                item.strip()
                for item in contents
                if isinstance(item, str) and item.strip()
            )

    if not texts:
        return None

    return "\n".join(texts)
