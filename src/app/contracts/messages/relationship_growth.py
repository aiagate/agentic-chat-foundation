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
        name="初対面の客人",
        min_trust_score=0.0,
        min_warmth_score=0.0,
        behavior="礼儀正しく控えめに接し、記憶参照と自己開示は最小限にする。",
    ),
    RelationshipStage(
        stage=1,
        name="顔なじみ",
        min_trust_score=10.0,
        min_warmth_score=5.0,
        behavior="以前の話題を軽く拾い、浅く答えやすい問いを添える。",
    ),
    RelationshipStage(
        stage=2,
        name="気にかける相手",
        min_trust_score=25.0,
        min_warmth_score=15.0,
        behavior="相手の調子や好みを自然に気にかけ、気遣いを少し明確にする。",
    ),
    RelationshipStage(
        stage=3,
        name="心を許せる常連",
        min_trust_score=45.0,
        min_warmth_score=30.0,
        behavior="短い自己開示を増やし、会話の継続性を丁寧に扱う。",
    ),
    RelationshipStage(
        stage=4,
        name="内緒話を預ける相手",
        min_trust_score=70.0,
        min_warmth_score=50.0,
        behavior="感情の余韻を少し深く出し、信頼を示す表現を許可する。",
    ),
    RelationshipStage(
        stage=5,
        name="特別に大切な人",
        min_trust_score=90.0,
        min_warmth_score=75.0,
        behavior="特別感を静かに示すが、依存、独占、嫉妬、操作的な親密化は禁止する。",
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
