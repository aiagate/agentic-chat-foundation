from datetime import UTC, datetime

from app.domain.services.relationship_recalculation import (
    RelationshipEventInput,
    recalculate_affection,
)


def test_recalculate_affection_applies_daily_positive_cap_in_stable_order() -> None:
    result = recalculate_affection(
        [
            RelationshipEventInput(
                id="later",
                proposed_delta=3,
                observed_at=datetime(2026, 7, 16, 12, tzinfo=UTC),
            ),
            RelationshipEventInput(
                id="earlier",
                proposed_delta=4,
                observed_at=datetime(2026, 7, 16, 9, tzinfo=UTC),
            ),
        ]
    )

    assert result.affection == 5
    assert [(item.id, item.applied_delta) for item in result.applied_events] == [
        ("earlier", 4),
        ("later", 1),
    ]


def test_recalculate_affection_applies_negative_cap_and_global_bounds() -> None:
    result = recalculate_affection(
        [
            RelationshipEventInput(
                id="negative",
                proposed_delta=-20,
                observed_at=datetime(2026, 7, 16, 9, tzinfo=UTC),
            ),
            RelationshipEventInput(
                id="positive",
                proposed_delta=200,
                observed_at=datetime(2026, 7, 17, 9, tzinfo=UTC),
            ),
        ]
    )

    assert result.affection == 5
    assert [(item.id, item.applied_delta) for item in result.applied_events] == [
        ("negative", 0),
        ("positive", 5),
    ]
