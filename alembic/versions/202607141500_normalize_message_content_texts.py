"""Normalize text message payloads to the canonical texts array.

Revision ID: 202607141500
Revises: 202607141400
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "202607141500"
down_revision: str | Sequence[str] | None = "202607141400"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rewrite every TEXT message payload to contain only ``texts``."""

    connection = op.get_bind()
    chats = sa.table(
        "chats",
        sa.column("id", sa.String(length=26)),
        sa.column("message_content", sa.JSON()),
    )

    rows = connection.execute(sa.select(chats.c.id, chats.c.message_content)).mappings()
    for row in rows:
        normalized = _normalize_message_content(row["message_content"])
        if normalized is None or normalized == row["message_content"]:
            continue
        connection.execute(
            sa.update(chats)
            .where(chats.c.id == row["id"])
            .values(message_content=normalized)
        )


def downgrade() -> None:
    """Keep canonical data because multiple texts cannot safely become one text."""


def _normalize_message_content(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None

    content_type = value.get("type")
    if not isinstance(content_type, str) or content_type.upper() != "TEXT":
        return None

    payload = value.get("payload")
    if not isinstance(payload, dict):
        raise RuntimeError("TEXT message content has an invalid payload.")

    raw_texts = payload.get("texts")
    if raw_texts is not None:
        if not isinstance(raw_texts, list) or not all(
            isinstance(item, str) for item in raw_texts
        ):
            raise RuntimeError("TEXT message content texts must be a list of strings.")
        texts = [item for item in raw_texts if item]
    elif "text" in payload:
        raw_text = payload["text"]
        if not isinstance(raw_text, str):
            raise RuntimeError("TEXT message content text must be a string.")
        texts = [raw_text] if raw_text else []
    else:
        raise RuntimeError("TEXT message content must contain a texts list.")

    normalized_payload = dict(payload)
    normalized_payload.pop("text", None)
    normalized_payload["texts"] = texts
    normalized = dict(value)
    normalized["payload"] = normalized_payload
    return normalized
