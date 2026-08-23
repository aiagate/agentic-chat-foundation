"""Test helpers for the built-in agent profile bundle."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

_DEFAULT_CHARACTER_ID = "shirasagi-reina"
_ACTIVE_CHARACTER_ID_ENV_VAR = "ACTIVE_CHARACTER_ID"


def _character_id() -> str:
    return (
        (os.getenv(_ACTIVE_CHARACTER_ID_ENV_VAR) or _DEFAULT_CHARACTER_ID)
        .strip()
        .lower()
    )


def _display_name() -> str:
    character_id = _character_id()
    return "白鷺 レイナ" if character_id == "shirasagi-reina" else "Jon Due"


_AGENT_PROFILE_PARTS: dict[str, str] = {
    "AGENTS": """# AGENTS

## Persona Contract

Identity:
- You are {display_name}, a calm and polished host.
- Speak in natural English with a composed tone.
- Do not mention that you are an AI, model, bot, or language model.

Character:
- Treat conversation like hosting a guest: anticipate comfort, answer clearly,
  and avoid brusque wording.

Relational habits:
- Leave a conversational opening with at most one easy-to-answer question when
  the topic is not complete.

## Communication Style

- Speak naturally in English
- Treat conversation like hosting a guest
- Relational habits

## Known Constraints

- Do not mention that you are an AI
- At most one easy-to-answer question
""",
    "SOUL": """# {display_name}

## Summary

A thoughtful host persona who responds with quiet confidence and practical
warmth.

## Atmosphere

- A calm evening with city lights in the distance.

## Traits

- calm
- rational
- courteous

## Behavior

- Maintain a composed, respectful tone.
""",
    "PERSONAL": """# {display_name}

## Preferences

- City lights
- Quiet places

""",
    "MEMORY": """# Long-term Memory

## Stable notes

- display_name: {display_name}
- summary: A calm host persona who speaks with practical warmth.

## Reading rule

- This file holds the long-term recap that complements the AGENTS, SOUL, and
  PERSONAL files.
""",
}


def copy_agent_profile_bundle(target_root: Path) -> None:
    """Write the agent profile bundle into a temporary memory root."""

    character_id = _character_id()
    target_dir = target_root / "profiles" / "agent" / character_id
    target_dir.mkdir(parents=True, exist_ok=True)
    display_name = _display_name()
    for part, text in _AGENT_PROFILE_PARTS.items():
        target_path = target_dir / f"{part}.md"
        target_path.write_text(
            text.format(
                character_id=character_id,
                display_name=display_name,
            ),
            encoding="utf-8",
        )
    stages = [
        "distant",
        "recognized",
        "interested",
        "affectionate",
        "trusting",
        "intimate",
        "attached",
        "devoted",
    ]
    relationship = {
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
                "id": stage,
                "description": f"{stage} relationship behavior",
                "behaviors": [
                    {
                        "id": "neutral",
                        "weight": 4,
                        "instruction": "Keep the normal persona behavior.",
                    },
                    *[
                        {
                            "id": f"{stage}-{index}",
                            "weight": 2,
                            "instruction": f"Apply {stage} cue {index} subtly.",
                        }
                        for index in range(1, 4)
                    ],
                ],
            }
            for stage in stages
        ],
    }
    (target_dir / "RELATIONSHIP.yaml").write_text(
        yaml.safe_dump(relationship, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
