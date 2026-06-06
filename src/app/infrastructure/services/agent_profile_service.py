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
    front_matter_string,
    front_matter_string_list,
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
        relationship_section = _section_key_values(
            personal_document.body, "Relationship"
        )
        profile = _load_profile(
            agents_document=agents_document,
            soul_document=soul_document,
            personal_document=personal_document,
        )
        character = _load_character_definition(
            character_id=self.character_id,
            agents_document=agents_document,
            soul_document=soul_document,
            personal_document=personal_document,
            relationship_section=relationship_section,
            profile=profile,
        )
        persona_context = agents_document.body.strip()
        communication_style = _body_section_list(
            agents_document.body, "Communication Style"
        )
        known_constraints = _body_section_list(
            agents_document.body, "Known Constraints"
        )
        atmosphere = _body_section_list(soul_document.body, "Atmosphere")
        behavior = _body_section_list(soul_document.body, "ふるまい")
        fallback = _body_section_list(personal_document.body, "Fallback")
        memory_reading_rules = _body_section_list(memory_document.body, "Reading rule")
        relationship_entity_id = character.relationship_entity_id
        relationship_entity_label = character.relationship_entity_label
        relationship_entity_type = character.relationship_entity_type
        relationship_tag = character.relationship_tag
        relationship_defaults = RelationshipDefaults(
            trust_score=_section_float(
                relationship_section,
                "relationship_initial_trust_score",
                default=character.relationship_defaults.trust_score,
            ),
            warmth_score=_section_float(
                relationship_section,
                "relationship_initial_warmth_score",
                default=character.relationship_defaults.warmth_score,
            ),
            stage=_section_int(
                relationship_section,
                "relationship_initial_stage",
                default=character.relationship_defaults.stage,
            ),
        )
        return AgentProfileBundle(
            profile=profile,
            character=character,
            persona_context=persona_context,
            communication_style=tuple(communication_style),
            known_constraints=tuple(known_constraints),
            atmosphere=tuple(atmosphere),
            behavior=tuple(behavior),
            relationship_entity_id=relationship_entity_id,
            relationship_entity_label=relationship_entity_label,
            relationship_entity_type=relationship_entity_type,
            relationship_tag=relationship_tag,
            relationship_defaults=relationship_defaults,
            relationship=tuple(
                _body_section_list(personal_document.body, "Relationship")
            ),
            fallback=tuple(fallback),
            memory_reading_rules=tuple(memory_reading_rules),
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


def _load_profile(
    *,
    agents_document: MemoryMarkdownDocument,
    soul_document: MemoryMarkdownDocument,
    personal_document: MemoryMarkdownDocument,
) -> MemoryProfile:
    display_name = (
        front_matter_string_or_none(agents_document.front_matter.get("display_name"))
        or _body_h1_text(agents_document.body)
        or _body_h1_text(soul_document.body)
        or _body_h1_text(personal_document.body)
    )
    summary = front_matter_string(
        soul_document.front_matter.get("summary")
    ) or _body_section_text(soul_document.body, "Summary")
    traits = front_matter_string_list(soul_document.front_matter.get("traits", []))
    if not traits:
        traits = _body_section_list(soul_document.body, "Traits")
    preferences = front_matter_string_list(
        personal_document.front_matter.get("preferences", [])
    )
    if not preferences:
        preferences = _body_section_list(personal_document.body, "Preferences")
    user_id = front_matter_string_or_none(agents_document.front_matter.get("user_id"))
    if not user_id:
        user_id = "ai"
    return MemoryProfile(
        user_id=user_id,
        display_name=display_name,
        summary=summary,
        traits=traits,
        preferences=preferences,
    )


def _load_character_definition(
    *,
    character_id: str,
    agents_document: MemoryMarkdownDocument,
    soul_document: MemoryMarkdownDocument,
    personal_document: MemoryMarkdownDocument,
    relationship_section: dict[str, str],
    profile: MemoryProfile,
) -> CharacterDefinition:
    display_name = profile.display_name or (
        front_matter_string_or_none(agents_document.front_matter.get("display_name"))
        or _body_h1_text(agents_document.body)
        or _body_h1_text(soul_document.body)
        or _body_h1_text(personal_document.body)
    )
    relationship_entity_id = relationship_section.get("relationship_entity_id")
    relationship_entity_label = relationship_section.get("relationship_entity_label")
    relationship_entity_type = relationship_section.get("relationship_entity_type")
    relationship_tag = relationship_section.get("relationship_tag")
    if not display_name:
        raise AgentProfileServiceError("agent profile bundle is missing a display name")
    if not relationship_entity_id or not relationship_entity_label:
        raise AgentProfileServiceError(
            "agent profile bundle is missing required relationship metadata"
        )
    return CharacterDefinition(
        character_id=character_id,
        display_name=display_name,
        relationship_entity_id=relationship_entity_id,
        relationship_entity_label=relationship_entity_label,
        relationship_entity_type=relationship_entity_type or "relationship",
        relationship_tag=relationship_tag or "agent-growth",
    )


def _body_section_text(body: str, section_name: str) -> str:
    lines = _body_section_lines(body, section_name)
    return "\n".join(line.strip() for line in lines).strip()


def _body_section_list(body: str, section_name: str) -> list[str]:
    lines = _body_section_lines(body, section_name)
    values: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- "):
            values.append(stripped[2:].strip())
    return values


def _body_section_lines(body: str, section_name: str) -> list[str]:
    if not body:
        return []
    lines = body.splitlines()
    captured: list[str] = []
    active = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            active = stripped[3:].strip().lower() == section_name.lower()
            continue
        if active:
            captured.append(line)
    return captured


def _body_h1_text(body: str) -> str | None:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            value = stripped[2:].strip()
            if value:
                return value
    return None


def _section_key_values(body: str, section_name: str) -> dict[str, str]:
    lines = _body_section_lines(body, section_name)
    values: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- ") and ":" in stripped:
            key, value = stripped[2:].split(":", 1)
            values[key.strip()] = value.strip()
    return values


def _section_float(
    values: dict[str, str],
    key: str,
    *,
    default: float,
) -> float:
    raw = values.get(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _section_int(
    values: dict[str, str],
    key: str,
    *,
    default: int,
) -> int:
    raw = values.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default
