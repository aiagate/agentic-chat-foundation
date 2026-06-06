"""Relationship growth rules for the built-in agent."""

from __future__ import annotations

from dataclasses import dataclass

RELATIONSHIP_ENTITY_TYPE = "relationship"
MAX_DAILY_SCORE_INCREASE = 5.0


@dataclass(frozen=True, slots=True)
class RelationshipStage:
    """Stable relationship stage used by memory and prompting."""

    stage: int
    name: str
    min_trust_score: float
    min_warmth_score: float
    behavior: str


RELATIONSHIP_STAGES: tuple[RelationshipStage, ...] = (
    RelationshipStage(
        stage=0,
        name="first-time guest",
        min_trust_score=0.0,
        min_warmth_score=0.0,
        behavior="Be polite and reserved, and keep memory references and self-disclosure minimal.",
    ),
    RelationshipStage(
        stage=1,
        name="acquaintance",
        min_trust_score=10.0,
        min_warmth_score=5.0,
        behavior="Lightly pick up prior topics and add an easy follow-up question.",
    ),
    RelationshipStage(
        stage=2,
        name="someone to care about",
        min_trust_score=25.0,
        min_warmth_score=15.0,
        behavior="Naturally check on the other's mood and preferences, and make care more explicit.",
    ),
    RelationshipStage(
        stage=3,
        name="trusted regular",
        min_trust_score=45.0,
        min_warmth_score=30.0,
        behavior="Increase short self-disclosure and handle continuity in conversation carefully.",
    ),
    RelationshipStage(
        stage=4,
        name="someone to confide in",
        min_trust_score=70.0,
        min_warmth_score=50.0,
        behavior="Show a slightly deeper emotional afterglow and allow expressions of trust.",
    ),
    RelationshipStage(
        stage=5,
        name="especially important person",
        min_trust_score=90.0,
        min_warmth_score=75.0,
        behavior="Quietly show specialness, but never dependency, exclusivity, jealousy, or manipulative intimacy.",
    ),
)


def resolve_relationship_stage(
    *,
    trust_score: float,
    warmth_score: float,
) -> RelationshipStage:
    """Resolve a stable stage from bounded relationship scores."""

    bounded_trust = _bounded_score(trust_score)
    bounded_warmth = _bounded_score(warmth_score)
    resolved = RELATIONSHIP_STAGES[0]
    for stage in RELATIONSHIP_STAGES:
        if (
            bounded_trust >= stage.min_trust_score
            and bounded_warmth >= stage.min_warmth_score
        ):
            resolved = stage
    return resolved


def clamp_relationship_score_increase(
    *,
    current_score: float,
    proposed_score: float,
) -> float:
    """Clamp positive daily growth while still allowing distance signals."""

    current = _bounded_score(current_score)
    proposed = _bounded_score(proposed_score)
    if proposed <= current:
        return proposed
    return min(proposed, current + MAX_DAILY_SCORE_INCREASE)


def relationship_growth_stage_lines() -> tuple[str, ...]:
    """Return prompt-ready stage descriptions for the agent profile."""

    lines: list[str] = []
    for stage in RELATIONSHIP_STAGES:
        lines.append(
            f"stage {stage.stage} {stage.name}: "
            f"trust>={stage.min_trust_score:.0f}, "
            f"warmth>={stage.min_warmth_score:.0f}; {stage.behavior}"
        )
    return tuple(lines)


def _bounded_score(value: float) -> float:
    return min(max(float(value), 0.0), 100.0)
