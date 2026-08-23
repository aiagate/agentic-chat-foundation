"""Shared valid relationship definitions for tests."""

from app.contracts.messages.relationship import CharacterRelationshipDefinition


def relationship_definition() -> CharacterRelationshipDefinition:
    """Return a minimal complete definition matching the production schema."""

    stage_ids = (
        "distant",
        "recognized",
        "interested",
        "affectionate",
        "trusting",
        "intimate",
        "attached",
        "devoted",
    )
    return CharacterRelationshipDefinition.model_validate(
        {
            "schema_version": 1,
            "signal_deltas": {
                "strong_negative": -5,
                "negative": -2,
                "neutral": 0,
                "positive": 1,
                "strong_positive": 3,
            },
            "stages": [
                {
                    "id": stage_id,
                    "description": f"{stage_id} behavior",
                    "behaviors": [
                        {
                            "id": "neutral",
                            "weight": 4,
                            "instruction": "Use the normal persona.",
                        },
                        *[
                            {
                                "id": f"cue-{index}",
                                "weight": 2,
                                "instruction": f"Use cue {index} subtly.",
                            }
                            for index in range(1, 4)
                        ],
                    ],
                }
                for stage_id in stage_ids
            ],
        }
    )
