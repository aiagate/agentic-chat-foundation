"""Tests for the shared relationship stage policy."""

import pytest

from app.domain.aggregates.character_relationship import (
    CharacterRelationship,
    RelationshipStageId,
    resolve_relationship_stage,
)


@pytest.mark.parametrize(
    ("affection", "expected"),
    [
        (0, RelationshipStageId.DISTANT),
        (10, RelationshipStageId.DISTANT),
        (11, RelationshipStageId.RECOGNIZED),
        (25, RelationshipStageId.RECOGNIZED),
        (26, RelationshipStageId.INTERESTED),
        (40, RelationshipStageId.INTERESTED),
        (41, RelationshipStageId.AFFECTIONATE),
        (55, RelationshipStageId.AFFECTIONATE),
        (56, RelationshipStageId.TRUSTING),
        (70, RelationshipStageId.TRUSTING),
        (71, RelationshipStageId.INTIMATE),
        (85, RelationshipStageId.INTIMATE),
        (86, RelationshipStageId.ATTACHED),
        (95, RelationshipStageId.ATTACHED),
        (96, RelationshipStageId.DEVOTED),
        (100, RelationshipStageId.DEVOTED),
    ],
)
def test_resolve_relationship_stage_boundaries(
    affection: int, expected: RelationshipStageId
) -> None:
    assert resolve_relationship_stage(affection) is expected


@pytest.mark.parametrize("affection", [-1, 101])
def test_relationship_rejects_out_of_range_affection(affection: int) -> None:
    with pytest.raises(ValueError, match="between 0 and 100"):
        CharacterRelationship("character", "user", affection=affection)
