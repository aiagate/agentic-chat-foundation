"""Filesystem-backed agent profile bundle loader."""

from __future__ import annotations

from dataclasses import dataclass

from app.contracts.messages.agent_profile import AgentProfileBundle
from app.contracts.messages.character_definition import (
    CharacterDefinition,
    RelationshipDefaults,
)
from app.contracts.messages.memory_context import MemoryProfile
from app.contracts.ports.agent_profile_service import (
    AgentProfileServiceError,
    IAgentProfileService,
)
from app.contracts.ports.memory_store import IMemoryStore
from app.infrastructure.memory.markdown import (
    MemoryMarkdownDocument,
    front_matter_string_or_none,
)


@dataclass(slots=True)
class FilesystemAgentProfileService(IAgentProfileService):
    """Load the built-in agent profile bundle from the filesystem."""

    store: IMemoryStore
    character_id: str

    def ensure_agent_profile_bundle(self) -> None:
        """Validate that the canonical bundle files exist and parse cleanly."""

        self.load_agent_profile_bundle()

    def load_agent_profile_bundle(self) -> AgentProfileBundle:
        """Return the parsed agent profile bundle."""

        agents_document = self._read_part("AGENTS")
        soul_document = self._read_part("SOUL")
        personal_document = self._read_part("PERSONAL")
        memory_document = self._read_part("MEMORY")
        profile = _load_profile()
        character = _load_character_definition(
            character_id=self.character_id,
            personal_document=personal_document,
        )
        persona_context = "\n\n".join(
            part
            for part in (
                agents_document.body.strip(),
                soul_document.body.strip(),
                personal_document.body.strip(),
                memory_document.body.strip(),
            )
            if part
        )
        relationship_defaults = RelationshipDefaults(
            trust_score=_front_matter_float(
                personal_document.front_matter,
                "relationship_initial_trust_score",
                default=character.relationship_defaults.trust_score,
            ),
            warmth_score=_front_matter_float(
                personal_document.front_matter,
                "relationship_initial_warmth_score",
                default=character.relationship_defaults.warmth_score,
            ),
            stage=_front_matter_int(
                personal_document.front_matter,
                "relationship_initial_stage",
                default=character.relationship_defaults.stage,
            ),
        )
        return AgentProfileBundle(
            profile=profile,
            character=character,
            persona_context=persona_context,
            relationship_entity_id=character.relationship_entity_id,
            relationship_entity_label=character.relationship_entity_label,
            relationship_entity_type=character.relationship_entity_type,
            relationship_tag=character.relationship_tag,
            relationship_defaults=relationship_defaults,
        )

    def _read_part(self, part: str) -> MemoryMarkdownDocument:
        path = self.store.agent_profile_part_path(
            part,
            character_id=self.character_id,
        )
        if path.exists():
            return self.store.read_document(path, expected_memory_type="profile")

        raise AgentProfileServiceError(
            f"agent profile bundle missing required file: {path}"
        )


def _load_profile() -> MemoryProfile:
    return MemoryProfile(user_id="ai")


def _load_character_definition(
    *,
    character_id: str,
    personal_document: MemoryMarkdownDocument,
) -> CharacterDefinition:
    relationship_entity_id = front_matter_string_or_none(
        personal_document.front_matter.get("relationship_entity_id")
    )
    relationship_entity_label = front_matter_string_or_none(
        personal_document.front_matter.get("relationship_entity_label")
    )
    relationship_entity_type = front_matter_string_or_none(
        personal_document.front_matter.get("relationship_entity_type")
    )
    relationship_tag = front_matter_string_or_none(
        personal_document.front_matter.get("relationship_tag")
    )
    if not relationship_entity_id or not relationship_entity_label:
        raise AgentProfileServiceError(
            "agent profile bundle is missing required relationship metadata"
        )
    return CharacterDefinition(
        character_id=character_id,
        relationship_entity_id=relationship_entity_id,
        relationship_entity_label=relationship_entity_label,
        relationship_entity_type=relationship_entity_type or "relationship",
        relationship_tag=relationship_tag or "agent-growth",
    )


def _front_matter_float(
    values: dict[str, object],
    key: str,
    *,
    default: float,
) -> float:
    raw = values.get(key)
    if not isinstance(raw, str | int | float):
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _front_matter_int(
    values: dict[str, object],
    key: str,
    *,
    default: int,
) -> int:
    raw = values.get(key)
    if not isinstance(raw, str | int | float):
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default
