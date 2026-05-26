"""Tests for deterministic memory decay scoring."""

from datetime import UTC, datetime

from app.infrastructure.services.memory_decay import calculate_decay_score


def test_decay_score_is_deterministic_for_same_inputs() -> None:
    """Decay should be a pure function of persisted fields and reference time."""
    front_matter: dict[str, object] = {
        "importance": 0.7,
        "confidence": 0.9,
        "updated_at": "2026-04-18T00:00:00+00:00",
        "access_count": 2,
        "retention_state": "active",
    }
    reference_time = datetime(2026, 5, 18, tzinfo=UTC)

    first = calculate_decay_score(front_matter, reference_time=reference_time)
    second = calculate_decay_score(front_matter, reference_time=reference_time)

    assert first == second


def test_decay_score_considers_pinned_age_access_and_retention() -> None:
    """Pinned and accessed memories should outrank stale archived memories."""
    reference_time = datetime(2026, 5, 18, tzinfo=UTC)
    old_archived: dict[str, object] = {
        "importance": 0.4,
        "confidence": 0.7,
        "updated_at": "2025-05-18T00:00:00+00:00",
        "access_count": 0,
        "retention_state": "archived",
    }
    old_accessed: dict[str, object] = {
        **old_archived,
        "access_count": 8,
        "last_accessed_at": "2026-05-17T00:00:00+00:00",
        "retention_state": "active",
    }
    pinned: dict[str, object] = {
        **old_archived,
        "pinned": True,
    }

    archived_score = calculate_decay_score(
        old_archived,
        reference_time=reference_time,
    )
    accessed_score = calculate_decay_score(
        old_accessed,
        reference_time=reference_time,
    )
    pinned_score = calculate_decay_score(pinned, reference_time=reference_time)

    assert accessed_score > archived_score
    assert pinned_score >= 0.85
    assert pinned_score > archived_score
