"""Deterministic retention decay scoring for memory documents."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from math import log1p


def calculate_decay_score(
    front_matter: Mapping[str, object],
    *,
    reference_time: datetime,
) -> float:
    """Return a deterministic score for retention and retrieval ranking."""

    normalized_reference = _as_utc(reference_time)
    importance = _clamp_float(front_matter.get("importance"), default=0.5)
    confidence = _clamp_float(front_matter.get("confidence"), default=1.0)
    pinned = front_matter.get("pinned") is True
    access_count = max(_int_value(front_matter.get("access_count")), 0)
    retention_state = str(front_matter.get("retention_state") or "active")

    age_time = _datetime_value(
        front_matter.get("occurred_at") or front_matter.get("updated_at")
    )
    age_days = _days_between(age_time, normalized_reference)
    age_factor = 1.0 / (1.0 + (age_days / 90.0))

    last_accessed_at = _datetime_value(front_matter.get("last_accessed_at"))
    access_recency = 0.0
    if last_accessed_at is not None:
        access_age_days = _days_between(last_accessed_at, normalized_reference)
        access_recency = 1.0 / (1.0 + (access_age_days / 30.0))

    access_factor = min(log1p(access_count) / 5.0, 0.25)
    retention_multiplier = _retention_multiplier(retention_state)

    score = (
        (0.40 * importance)
        + (0.30 * confidence)
        + (0.20 * age_factor)
        + (0.05 * access_recency)
        + access_factor
    ) * retention_multiplier

    if pinned:
        score = max(score + 0.20, 0.85)

    return round(min(max(score, 0.0), 1.0), 6)


def _retention_multiplier(retention_state: str) -> float:
    if retention_state == "compressed":
        return 0.65
    if retention_state == "archived":
        return 0.25
    return 1.0


def _clamp_float(value: object, *, default: float) -> float:
    if value is None:
        return default
    if not isinstance(value, str | int | float):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, 0.0), 1.0)


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _datetime_value(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return _as_utc(value)
    if not isinstance(value, str) or not value:
        return None
    try:
        return _as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _days_between(start: datetime | None, end: datetime) -> float:
    if start is None:
        return 365.0
    return max((end - _as_utc(start)).total_seconds() / 86_400.0, 0.0)
