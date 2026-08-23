"""Tests for the message content data migration."""

from importlib import util
from pathlib import Path
from typing import Any

import pytest

_migration_path = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "202607141500_normalize_message_content_texts.py"
)
_migration_spec = util.spec_from_file_location(
    "message_content_migration", _migration_path
)
if _migration_spec is None or _migration_spec.loader is None:
    raise RuntimeError("Could not load message content migration.")
_migration = util.module_from_spec(_migration_spec)
_migration_spec.loader.exec_module(_migration)


def _normalize(value: object) -> dict[str, Any] | None:
    return _migration._normalize_message_content(value)


def test_migration_converts_legacy_text_payload() -> None:
    assert _normalize(
        {
            "type": "TEXT",
            "payload": {"text": "legacy", "provider": "discord"},
        }
    ) == {
        "type": "TEXT",
        "payload": {"texts": ["legacy"], "provider": "discord"},
    }


def test_migration_preserves_canonical_text_payload() -> None:
    value = {"type": "TEXT", "payload": {"texts": ["hello", "follow-up"]}}

    assert _normalize(value) == value


def test_migration_ignores_non_text_payloads() -> None:
    value = {"type": "IMAGE", "payload": {"image_id": "image-1"}}

    assert _normalize(value) is None


def test_migration_rejects_malformed_text_payload() -> None:
    with pytest.raises(RuntimeError, match="texts list"):
        _normalize({"type": "TEXT", "payload": {"caption": "missing text"}})
