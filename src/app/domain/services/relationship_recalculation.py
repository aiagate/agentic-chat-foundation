"""Pure relationship affection recalculation policy."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.domain.aggregates.character_relationship import (
    MAX_DAILY_AFFECTION_DECREASE,
    MAX_DAILY_AFFECTION_INCREASE,
    clamp_affection,
)

_JST = ZoneInfo("Asia/Tokyo")


@dataclass(frozen=True, slots=True)
class RelationshipEventInput:
    """Persistence-independent event data used by the affection policy."""

    id: str
    proposed_delta: int
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class AppliedRelationshipEvent:
    """Applied delta calculated for one active relationship event."""

    id: str
    applied_delta: int


@dataclass(frozen=True, slots=True)
class RelationshipRecalculation:
    """Result of replaying all active relationship events."""

    affection: int
    applied_events: tuple[AppliedRelationshipEvent, ...]


def recalculate_affection(
    events: Sequence[RelationshipEventInput],
) -> RelationshipRecalculation:
    """Replay active events in stable order and apply daily/domain bounds."""

    ordered = sorted(
        events,
        key=lambda event: (_as_utc(event.observed_at), event.id),
    )
    affection = 0
    positive_by_day: dict[date, int] = {}
    negative_by_day: dict[date, int] = {}
    applied_events: list[AppliedRelationshipEvent] = []

    for event in ordered:
        day = _as_utc(event.observed_at).astimezone(_JST).date()
        proposed = event.proposed_delta
        if proposed > 0:
            remaining = MAX_DAILY_AFFECTION_INCREASE - positive_by_day.get(day, 0)
            applied = min(proposed, max(remaining, 0))
            positive_by_day[day] = positive_by_day.get(day, 0) + applied
        elif proposed < 0:
            remaining = MAX_DAILY_AFFECTION_DECREASE - negative_by_day.get(day, 0)
            applied = -min(abs(proposed), max(remaining, 0))
            negative_by_day[day] = negative_by_day.get(day, 0) + abs(applied)
        else:
            applied = 0

        bounded = clamp_affection(affection + applied)
        applied_events.append(
            AppliedRelationshipEvent(
                id=event.id,
                applied_delta=bounded - affection,
            )
        )
        affection = bounded

    return RelationshipRecalculation(
        affection=affection,
        applied_events=tuple(applied_events),
    )


def _as_utc(value: datetime) -> datetime:
    return (
        value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
    )
